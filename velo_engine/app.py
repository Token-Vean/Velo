"""Aplicación web local de Velo."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import time
import uuid

from flask import Flask, g, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from velo_engine.constants import (
    APP_VERSION,
    MAX_CONTENT_LENGTH,
    MAX_TEXT_LENGTH,
    SESSION_TTL_HOURS,
)
from velo_engine.detector import build_envelope, detect, spacy_status
from velo_engine.reader import read_file, supported_extensions
from velo_engine.security import init_security, log_audit, hash_text
from velo_engine.visual import (
    apply_redactions_to_original,
    export_visual_redacted_pdf,
    load_applied_metadata,
    read_pdf_for_visual_review,
    visual_capabilities,
)

logger = logging.getLogger("velo.app")

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Seguridad
init_security(app)

ALLOWED_EXTENSIONS = {".txt", ".docx", ".pdf"}


def _allowed_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def _sanitize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "", value or "")[:64]


def _workspace_dir() -> str:
    workspace = app.config.get("WORKSPACE", os.path.join(os.path.dirname(__file__), "..", "workspace"))
    workspace = os.path.abspath(workspace)
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _sessions_root() -> str:
    root = os.path.join(_workspace_dir(), "sessions")
    os.makedirs(root, exist_ok=True)
    return root


def _session_dir(session_id: str, *, create: bool = True) -> str:
    safe_id = _sanitize_id(session_id)
    if not safe_id:
        raise ValueError("session_id inválido")
    directory = os.path.abspath(os.path.join(_sessions_root(), safe_id))
    if not directory.startswith(_sessions_root()):
        raise ValueError("Ruta de sesión inválida")
    if create:
        os.makedirs(directory, exist_ok=True)
    return directory


def _cleanup_session(session_id: str | None) -> None:
    if not session_id:
        return
    safe_id = _sanitize_id(session_id)
    if not safe_id:
        return
    path = os.path.abspath(os.path.join(_sessions_root(), safe_id))
    if path.startswith(_sessions_root()) and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def prune_stale_sessions(ttl_hours: int = SESSION_TTL_HOURS) -> int:
    cutoff = time.time() - ttl_hours * 3600
    removed = 0

    for name in os.listdir(_sessions_root()):
        path = os.path.join(_sessions_root(), name)
        if not os.path.isdir(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1

    return removed


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(exc):
    max_mb = app.config.get("MAX_CONTENT_LENGTH", 0) / (1024 * 1024)
    logger.warning("Fichero rechazado: excede el tamaño máximo de %.0f MB", max_mb)
    return jsonify({
        "error": f"El fichero excede el tamaño máximo permitido ({max_mb:.0f} MB)."
    }), 413


@app.route("/")
def index():
    return render_template(
        "index.html",
        formats=supported_extensions(),
        app_version=APP_VERSION,
        csrf_token=getattr(g, "csrf_token", ""),
    )


@app.route("/api/analyze/text", methods=["POST"])
def analyze_text():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Petición inválida."}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No se ha proporcionado texto."}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"error": f"Texto demasiado largo ({len(text)} caracteres). Máximo: {MAX_TEXT_LENGTH}."}), 400

    log_audit("analyze_text", f"HASH={hash_text(text)} LEN={len(text)}")
    result = detect(text)
    return jsonify(
        {
            "success": True,
            "text": text,
            "format": "txt",
            "visual_available": False,
            "visual_reason": "La revisión visual solo está disponible para PDF.",
            **result,
        }
    )


@app.route("/api/analyze/file", methods=["POST"])
def analyze_file():
    if "file" not in request.files:
        return jsonify({"error": "No se ha enviado ningún fichero."}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "Nombre de fichero vacío."}), 400
    if not _allowed_file(file.filename):
        logger.warning("Formato rechazado: %s", file.filename)
        return jsonify({"error": "Formato no permitido. Use TXT, DOCX o PDF."}), 400

    original_name = secure_filename(file.filename) or "document"
    ext = os.path.splitext(original_name)[1].lower()

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    file_size_mb = file_size / (1024 * 1024)
    logger.info("Fichero recibido: %s (%.1f MB)", original_name, file_size_mb)

    visual_caps = visual_capabilities()

    if ext == ".pdf" and visual_caps.get("fitz") and visual_caps.get("pillow"):
        session_id = uuid.uuid4().hex[:16]
        session_dir = _session_dir(session_id)
        pdf_path = os.path.join(session_dir, "original.pdf")
        file.save(pdf_path)

        try:
            text, fmt, error, visual_meta = read_pdf_for_visual_review(pdf_path, session_dir, session_id)
        except Exception:
            logger.exception(
                "Error al preparar revisión visual (fichero=%s, tamaño=%.1f MB)",
                original_name,
                file_size_mb,
            )
            _cleanup_session(session_id)
            return jsonify({"error": "Error al preparar la revisión visual del PDF."}), 400

        if error:
            logger.warning("Error en extracción PDF visual: %s (fichero=%s)", error, original_name)
            _cleanup_session(session_id)
            return jsonify({"error": error}), 400
        if not text:
            logger.warning("Sin texto extraído de PDF visual (fichero=%s)", original_name)
            _cleanup_session(session_id)
            return jsonify({"error": "No se pudo extraer texto del PDF."}), 400
        if len(text) > MAX_TEXT_LENGTH:
            logger.warning(
                "Texto extraído excede el límite: %d caracteres (máx: %d, fichero=%s)",
                len(text), MAX_TEXT_LENGTH, original_name,
            )
            _cleanup_session(session_id)
            return jsonify({"error": f"Texto extraído demasiado largo ({len(text):,} caracteres). Máximo: {MAX_TEXT_LENGTH:,}."}), 400

        log_audit("analyze_file", f"FILE={original_name} HASH={hash_text(text)} MODE=visual")
        result = detect(text)
        return jsonify(
            {
                "success": True,
                "filename": file.filename,
                "format": fmt,
                "text": text,
                "visual_available": True,
                "visual_session": session_id,
                "visual_pages": visual_meta["pages"],
                "visual_mode": visual_meta["mode"],
                "visual_ocr_used": visual_meta["ocr_used"],
                **result,
            }
        )

    workspace = _workspace_dir()
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(workspace, safe_name)
    file.save(filepath)

    try:
        text, fmt, error = read_file(filepath)
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass

    if error:
        logger.warning("Error en extracción de fichero: %s (fichero=%s)", error, original_name)
        return jsonify({"error": error}), 400
    if not text:
        logger.warning("Sin texto extraído (fichero=%s)", original_name)
        return jsonify({"error": "No se pudo extraer texto del fichero."}), 400
    if len(text) > MAX_TEXT_LENGTH:
        logger.warning(
            "Texto extraído excede el límite: %d caracteres (máx: %d, fichero=%s)",
            len(text), MAX_TEXT_LENGTH, original_name,
        )
        return jsonify({"error": f"Texto extraído demasiado largo ({len(text):,} caracteres). Máximo: {MAX_TEXT_LENGTH:,}."}), 400

    log_audit("analyze_file", f"FILE={original_name} HASH={hash_text(text)}")
    result = detect(text)
    return jsonify(
        {
            "success": True,
            "filename": file.filename,
            "format": fmt,
            "text": text,
            "visual_available": False,
            "visual_reason": "La revisión visual solo está disponible para PDF.",
            **result,
        }
    )


@app.route("/api/export", methods=["POST"])
def export_envelope():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Petición inválida."}), 400

    raw_id = data.get("document_id", f"DOC-{uuid.uuid4().hex[:8].upper()}")
    document_id = _sanitize_id(raw_id) or f"DOC-{uuid.uuid4().hex[:8].upper()}"
    findings = data.get("findings", [])
    layers_active = data.get("layers_active", ["regex"])
    layers_available = data.get("layers_available", ["regex"])

    if not isinstance(findings, list):
        return jsonify({"error": "Formato de hallazgos no válido."}), 400

    log_audit("export", f"DOC={document_id} FINDINGS={len(findings)}")
    envelope = build_envelope(document_id, findings, layers_active, layers_available)
    workspace = _workspace_dir()
    export_filename = f"{document_id}_pii_report.json"
    export_path = os.path.join(workspace, export_filename)

    if not os.path.abspath(export_path).startswith(workspace):
        return jsonify({"error": "Ruta de exportación no válida."}), 400

    with open(export_path, "w", encoding="utf-8") as f_handle:
        json.dump(envelope, f_handle, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "envelope": envelope})


@app.route("/api/session/apply-original", methods=["POST"])
def apply_original_redactions():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Petición inválida."}), 400

    session_id = _sanitize_id(data.get("session_id"))
    findings = data.get("findings", [])
    if not session_id:
        return jsonify({"error": "No hay sesión visual activa para aplicar la edición sobre el original."}), 400
    if not isinstance(findings, list):
        return jsonify({"error": "Formato de hallazgos no válido."}), 400

    session_dir = _session_dir(session_id, create=False)
    if not os.path.isdir(session_dir):
        return jsonify({"error": "La sesión visual ya no existe o ha caducado."}), 404
    try:
        applied = apply_redactions_to_original(session_dir, session_id, findings)
    except Exception:
        logger.exception("No se pudo aplicar la edición sobre el original")
        return jsonify({"error": "No se pudo aplicar la edición sobre el original."}), 400

    return jsonify({"success": True, "applied": applied})


@app.route("/api/session/<session_id>/applied-original-pdf")
def download_applied_original_pdf(session_id):
    safe_id = _sanitize_id(session_id)
    if not safe_id:
        return jsonify({"error": "Sesión inválida."}), 400
    session_dir = _session_dir(safe_id, create=False)
    if not os.path.isdir(session_dir):
        return jsonify({"error": "La sesión visual ya no existe o ha caducado."}), 404
    try:
        applied = load_applied_metadata(session_dir)
    except Exception:
        return jsonify({"error": "No existe todavía una versión editada del original en esta sesión."}), 404

    output_path = os.path.join(session_dir, applied.get("pdf_name", "original_redacted.pdf"))
    if not os.path.exists(output_path):
        return jsonify({"error": "No existe todavía una versión editada del original en esta sesión."}), 404

    with open(output_path, "rb") as handle:
        pdf_bytes = handle.read()
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=applied.get("pdf_name", "original_redacted.pdf"),
    )


@app.route("/api/export/redacted-pdf", methods=["POST"])
def export_redacted_pdf():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Petición inválida."}), 400

    session_id = _sanitize_id(data.get("session_id"))
    findings = data.get("findings", [])
    document_id = _sanitize_id(data.get("document_id", f"DOC-{uuid.uuid4().hex[:8].upper()}"))
    if not session_id:
        return jsonify({"error": "No hay sesión visual activa para exportar el PDF original."}), 400
    if not isinstance(findings, list):
        return jsonify({"error": "Formato de hallazgos no válido."}), 400

    session_dir = _session_dir(session_id, create=False)
    if not os.path.isdir(session_dir):
        return jsonify({"error": "La sesión visual ya no existe o ha caducado."}), 404
    output_name = f"{document_id or 'DOC'}_visual_redacted.pdf"
    output_path = os.path.join(session_dir, output_name)

    try:
        export_visual_redacted_pdf(session_dir, findings, output_path)
    except Exception:
        logger.exception("No se pudo exportar el PDF visual")
        return jsonify({"error": "No se pudo exportar el PDF visual."}), 400

    with open(output_path, "rb") as handle:
        pdf_bytes = handle.read()
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=output_name,
    )


@app.route("/api/session/<session_id>/asset/<filename>")
def serve_session_asset(session_id, filename):
    safe_id = _sanitize_id(session_id)
    safe_file = os.path.basename(filename)
    if not safe_id:
        return jsonify({"error": "Sesión inválida."}), 400

    session_dir = _session_dir(safe_id, create=False)
    if not os.path.isdir(session_dir):
        return jsonify({"error": "La sesión visual ya no existe o ha caducado."}), 404

    assets_dir = os.path.join(session_dir, "assets")
    if not os.path.isdir(assets_dir):
        return jsonify({"error": "No existen assets para esta sesión."}), 404

    if not safe_file.endswith(".png"):
        return jsonify({"error": "Tipo de asset no permitido."}), 403
    return send_from_directory(assets_dir, safe_file)


@app.route("/api/session/cleanup", methods=["POST"])
def cleanup_session():
    data = request.get_json(silent=True) or {}
    _cleanup_session(data.get("session_id"))
    return jsonify({"success": True})


@app.route("/api/status")
def status():
    spacy = spacy_status()
    visual = visual_capabilities()
    layers = {
        "regex": True,
        "spacy": spacy["installed"],
        "spacy_model": spacy["model"],
    }
    return jsonify(
        {
            "tool": "velo",
            "version": APP_VERSION,
            "execution": "local",
            "layers": layers,
            "formats": supported_extensions(),
            "visual_redaction": {
                "implemented": bool(visual.get("fitz") and visual.get("pillow")),
                "fitz": visual.get("fitz"),
                "pillow": visual.get("pillow"),
                "ocr": visual.get("tesseract_ready"),
                "note": "La revisión visual de PDF usa la imagen original por página y coordina los tachados con la base textual/OCR de esa misma sesión.",
            },
        }
    )


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    import signal
    import threading

    pid = app.config.get("SERVER_PID", os.getpid())

    log_audit("shutdown")

    def _shutdown_later():
        try:
            sessions_root = _sessions_root()
            for name in os.listdir(sessions_root):
                path = os.path.join(sessions_root, name)
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error al limpiar sesiones durante el apagado: %s",
                exc,
                exc_info=True,
            )
        time.sleep(0.5)
        os.kill(pid, signal.SIGINT)

    threading.Thread(target=_shutdown_later, daemon=True).start()
    return jsonify({"success": True, "message": "Apagando Velo..."})
