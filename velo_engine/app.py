"""Aplicación web local de Velo."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import safe_join

from velo_engine.constants import (
    APP_VERSION,
    EXPORT_REPORT_TTL_HOURS,
    MAX_CONTENT_LENGTH,
    MAX_FINDINGS,
    MAX_TEXT_LENGTH,
    ORPHAN_UPLOAD_TTL_SECONDS,
    SESSION_TTL_HOURS,
)
from velo_engine.detector import build_envelope, detect, spacy_status
from velo_engine.file_guard import FileValidationError, validate_uploaded_file
from velo_engine.reader import docx_review_notes, read_file, supported_extensions
from velo_engine.security import hash_text, init_security, log_audit, para_log
from velo_engine.visual import (
    apply_redactions_to_original,
    export_native_redacted_pdf,
    load_session_metadata,
    signature_for_findings,
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
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Za-z0-9_\-]", "", value)[:64]


_FINDING_STATUSES = {"pending", "confirmed", "discarded"}


def _clean_findings(raw) -> list[dict] | None:
    """Normaliza los hallazgos que envía el navegador.

    Devuelve None si la estructura no es válida. Evita errores 500 (y
    excepciones en los módulos de redacción) con datos mal formados y limita
    el volumen procesable.
    """
    if not isinstance(raw, list) or len(raw) > MAX_FINDINGS:
        return None
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        position = item.get("position")
        if not isinstance(position, dict):
            return None
        start, end = position.get("start"), position.get("end")
        if (
            not isinstance(start, int) or not isinstance(end, int)
            or isinstance(start, bool) or isinstance(end, bool)
            or start < 0 or end <= start or end > MAX_TEXT_LENGTH
        ):
            return None
        status = item.get("status")
        if not isinstance(status, str) or status not in _FINDING_STATUSES:
            return None
        cleaned.append({
            **{k: v for k, v in item.items() if k != "position"},
            "id": str(item.get("id", ""))[:32],
            "status": status,
            "position": {"start": start, "end": end},
        })
    return cleaned


def _detect_or_error(text: str):
    """Ejecuta el detector y rechaza resultados inmanejables en la interfaz."""
    result = detect(text)
    if len(result["findings"]) > MAX_FINDINGS:
        return None, (
            f"El documento genera más de {MAX_FINDINGS:,} hallazgos y no puede revisarse "
            "con garantías en la interfaz. Divídalo en partes más pequeñas."
        )
    return result, None


def _is_within(root: str, path: str) -> bool:
    """Comprueba que ``path`` está contenido en ``root``.

    Sustituye a las comprobaciones ``startswith(root)``, vulnerables al
    clásico problema de prefijo (``/workspace-otro`` pasa un filtro
    ``startswith('/workspace')``). ``commonpath`` compara componentes de
    ruta completos.
    """
    try:
        root_abs = os.path.abspath(root)
        path_abs = os.path.abspath(path)
        return os.path.commonpath([root_abs, path_abs]) == root_abs
    except ValueError:
        # Unidades distintas en Windows u otras rutas incomparables.
        return False


def _workspace_dir() -> str:
    workspace = app.config.get("WORKSPACE", os.path.join(os.path.dirname(__file__), "..", "workspace"))
    workspace = os.path.abspath(workspace)
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _sessions_root() -> str:
    root = os.path.join(_workspace_dir(), "sessions")
    os.makedirs(root, exist_ok=True)
    return root


def _existing_session_dir(session_id: str) -> str | None:
    """Localiza una sesión creada por Velo entre los directorios reales del workspace."""
    with os.scandir(_sessions_root()) as entries:
        for entry in entries:
            if entry.name == session_id and entry.is_dir(follow_symlinks=False):
                return entry.path
    return None


def _cleanup_session(session_id: str | None) -> None:
    if session_id:
        directory = _existing_session_dir(session_id)
        if directory:
            shutil.rmtree(directory, ignore_errors=True)


def _log_file_guard_warnings(warnings: tuple[str, ...] | list[str]) -> None:
    """Registra advertencias locales no bloqueantes emitidas por file_guard."""
    for warning in warnings:
        logger.warning("Advertencia de entorno local: %s", warning)


def _remove_temp_file(filepath: str) -> None:
    """Elimina un fichero temporal sin ocultar errores en el log."""
    try:
        os.remove(filepath)
    except OSError as exc:
        logger.debug(
            "No se pudo eliminar el fichero temporal %s: %s",
            filepath,
            exc,
            exc_info=True,
        )


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


_ORPHAN_UPLOAD_RE = re.compile(r"^[0-9a-f]{12}\.(?:txt|docx|pdf)$")


def prune_orphan_uploads(max_age_seconds: int = ORPHAN_UPLOAD_TTL_SECONDS) -> int:
    """Elimina subidas temporales huérfanas del workspace.

    Los TXT/DOCX/PDF sin revisión visual se guardan un instante en el
    workspace con nombre aleatorio y se borran tras leerlos. Si el proceso
    muere a mitad (cierre de la ventana, corte de luz), el documento original
    quedaba ahí indefinidamente.
    """
    workspace = _workspace_dir()
    cutoff = time.time() - max_age_seconds
    removed = 0
    try:
        names = os.listdir(workspace)
    except OSError:
        return 0
    for name in names:
        if not _ORPHAN_UPLOAD_RE.match(name):
            continue
        path = os.path.join(workspace, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("Subidas temporales huérfanas eliminadas: %d", removed)
    return removed


def prune_stale_export_reports(ttl_hours: int = EXPORT_REPORT_TTL_HOURS) -> int:
    """Purga informes ``*_pii_report.json`` antiguos del workspace.

    Hasta la 0.4.x estos informes se acumulaban indefinidamente; además de
    consumir disco, son metadatos sensibles (texto de los hallazgos) que no
    deben persistir más de lo necesario en una herramienta local-first.
    """
    workspace = _workspace_dir()
    cutoff = time.time() - ttl_hours * 3600
    removed = 0

    try:
        names = os.listdir(workspace)
    except OSError:
        return 0

    for name in names:
        if not name.endswith("_pii_report.json"):
            continue
        path = os.path.join(workspace, name)
        if not os.path.isfile(path) or not _is_within(workspace, path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue

    if removed:
        logger.info("Informes de exportación antiguos eliminados: %d", removed)
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
    result, detect_error = _detect_or_error(text)
    if detect_error:
        return jsonify({"error": detect_error}), 400
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
        # Solo la extensión: el nombre original suele llevar nombres o DNI.
        logger.warning("Formato rechazado: extensión %s", para_log(os.path.splitext(file.filename)[1].lower(), 16))
        return jsonify({"error": "Formato no permitido. Use TXT, DOCX o PDF."}), 400

    # La extensión sale del nombre original (ya validado por _allowed_file).
    # Antes se tomaba de secure_filename(), que elimina caracteres no ASCII:
    # "数据.pdf" quedaba en "pdf", sin extensión, y el fichero se rechazaba.
    # El nombre original no se usa más allá de la extensión: suele contener
    # nombres o DNI y no debe llegar a disco ni a los logs.
    ext = os.path.splitext(file.filename)[1].lower()
    original_name = f"document{ext}"
    file_ref = uuid.uuid4().hex[:12]

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    file_size_mb = file_size / (1024 * 1024)
    logger.info("Fichero recibido: REF=%s (%.1f MB)", file_ref, file_size_mb)

    visual_caps = visual_capabilities()

    if ext == ".pdf" and visual_caps.get("fitz") and visual_caps.get("pillow"):
        session_id = uuid.uuid4().hex[:16]
        session_dir = os.path.join(_sessions_root(), session_id)
        os.mkdir(session_dir, mode=0o700)
        pdf_path = os.path.join(session_dir, "original.pdf")
        file.save(pdf_path)

        try:
            validation = validate_uploaded_file(
                pdf_path,
                original_name,
                max_bytes=app.config.get("MAX_CONTENT_LENGTH"),
            )
            _log_file_guard_warnings(validation.warnings)
        except FileValidationError as exc:
            logger.warning("Fichero rechazado por validación previa: REF=%s: %s", file_ref, exc.safe_message)
            _cleanup_session(session_id)
            return jsonify({"error": exc.safe_message}), 400

        try:
            text, fmt, error, visual_meta = read_pdf_for_visual_review(pdf_path, session_dir, session_id)
        except Exception:
            logger.exception(
                "Error al preparar revisión visual (ref=%s, tamaño=%.1f MB)",
                file_ref,
                file_size_mb,
            )
            _cleanup_session(session_id)
            return jsonify({"error": "Error al preparar la revisión visual del PDF."}), 400

        if error:
            logger.warning("Error en extracción PDF visual: %s (ref=%s)", error, file_ref)
            _cleanup_session(session_id)
            return jsonify({"error": error}), 400
        if not text:
            logger.warning("Sin texto extraído de PDF visual (ref=%s)", file_ref)
            _cleanup_session(session_id)
            return jsonify({"error": "No se pudo extraer texto del PDF."}), 400
        if len(text) > MAX_TEXT_LENGTH:
            logger.warning(
                "Texto extraído excede el límite: %d caracteres (máx: %d, ref=%s)",
                len(text), MAX_TEXT_LENGTH, file_ref,
            )
            _cleanup_session(session_id)
            return jsonify({"error": f"Texto extraído demasiado largo ({len(text):,} caracteres). Máximo: {MAX_TEXT_LENGTH:,}."}), 400

        log_audit("analyze_file", f"REF={file_ref} HASH={hash_text(text)} MODE=visual")
        result, detect_error = _detect_or_error(text)
        if detect_error:
            _cleanup_session(session_id)
            return jsonify({"error": detect_error}), 400
        return jsonify(
            {
                "success": True,
                "filename": file.filename,
                "format": fmt,
                "text": text,
                "visual_available": True,
                "visual_session": session_id,
                "visual_pages": visual_meta["pages"],
                "extraction_notes": [p["coverage_note"] for p in visual_meta["pages"] if p.get("coverage_note")],
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
        validation = validate_uploaded_file(
            filepath,
            original_name,
            max_bytes=app.config.get("MAX_CONTENT_LENGTH"),
        )
        _log_file_guard_warnings(validation.warnings)
    except FileValidationError as exc:
        logger.warning("Fichero rechazado por validación previa: %s", exc.safe_message)
        _remove_temp_file(filepath)
        return jsonify({"error": exc.safe_message}), 400

    notes: list[str] = []
    try:
        text, fmt, error = read_file(filepath)
        if not error and ext == ".docx":
            notes = docx_review_notes(filepath)
        elif not error and ext == ".pdf":
            notes = ["Solo se ha extraído texto. Revise en el original las imágenes y páginas escaneadas."]
    finally:
        _remove_temp_file(filepath)

    if error:
        logger.warning("Error en extracción de fichero: %s (ref=%s)", error, file_ref)
        return jsonify({"error": error}), 400
    if not text:
        logger.warning("Sin texto extraído (ref=%s)", file_ref)
        return jsonify({"error": "No se pudo extraer texto del fichero."}), 400
    if len(text) > MAX_TEXT_LENGTH:
        logger.warning(
            "Texto extraído excede el límite: %d caracteres (máx: %d, ref=%s)",
            len(text), MAX_TEXT_LENGTH, file_ref,
        )
        return jsonify({"error": f"Texto extraído demasiado largo ({len(text):,} caracteres). Máximo: {MAX_TEXT_LENGTH:,}."}), 400

    log_audit("analyze_file", f"REF={file_ref} HASH={hash_text(text)}")
    result, detect_error = _detect_or_error(text)
    if detect_error:
        return jsonify({"error": detect_error}), 400
    return jsonify(
        {
            "success": True,
            "filename": file.filename,
            "format": fmt,
            "text": text,
            "visual_available": False,
            "visual_reason": "La revisión visual solo está disponible para PDF.",
            "extraction_notes": notes,
            **result,
        }
    )


@app.route("/api/export", methods=["POST"])
def export_envelope():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Petición inválida."}), 400

    raw_id = data.get("document_id", f"DOC-{uuid.uuid4().hex[:8].upper()}")
    document_id = _sanitize_id(raw_id) or f"DOC-{uuid.uuid4().hex[:8].upper()}"
    findings = _clean_findings(data.get("findings", []))
    layers_active = data.get("layers_active", ["regex"])
    layers_available = data.get("layers_available", ["regex"])

    if findings is None:
        return jsonify({"error": "Formato de hallazgos no válido."}), 400
    if not isinstance(layers_active, list) or not isinstance(layers_available, list):
        return jsonify({"error": "Formato de capas no válido."}), 400
    layers_active = [str(item)[:32] for item in layers_active[:8]]
    layers_available = [str(item)[:32] for item in layers_available[:8]]

    stamp = data.get("analysis_date")
    if stamp is not None:
        try:
            datetime.fromisoformat(stamp)
        except (ValueError, TypeError):
            return jsonify({"error": "Fecha de análisis inválida."}), 400
    notes = data.get("extraction_notes", [])
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        return jsonify({"error": "Avisos de cobertura inválidos."}), 400
    source_format = data.get("source_format")
    if source_format not in (None, "txt", "pdf", "docx"):
        return jsonify({"error": "Formato de origen inválido."}), 400
    envelope = build_envelope(document_id, findings, layers_active, layers_available, stamp)
    envelope.update(source_format=source_format, extraction_notes=notes,
                    visual_review={"session_active": False}, original_application={"generated": False})
    assessment = data.get("risk_assessment_note", "")
    if not isinstance(assessment, str) or len(assessment) > 2000:
        return jsonify(error="La valoración profesional admite hasta 2.000 caracteres."), 400
    envelope["audit"]["residual_risk_reviewed"] = data.get("risk_reviewed") is True
    envelope["audit"]["residual_risk_note"] = assessment
    session_id = _sanitize_id(data.get("session_id"))
    if session_id:
        directory = _existing_session_dir(session_id)
        if directory is None:
            return jsonify(error="La sesión visual ha caducado. Analice de nuevo el PDF."), 409
        try:
            meta = load_session_metadata(directory)
            envelope["visual_review"] = {"session_active": True, "mode": meta["mode"], "page_count": meta["page_count"]}
            try:
                applied = load_applied_metadata(directory)
            except FileNotFoundError:
                applied = {}
        except (OSError, ValueError):
            return jsonify({"error": "La sesión visual ha caducado. Analice de nuevo el PDF."}), 409
        envelope["extraction_notes"] = [p["coverage_note"] for p in meta["pages"] if p.get("coverage_note")]
        if applied.get("findings_signature") == signature_for_findings(findings):
            envelope["original_application"] = {
                "generated": True, "mode": "image", "page_count": applied["page_count"],
                "total_rectangles": applied["total_rectangles"], "projection": applied.get("projection"),
                "issues": applied.get("issues"), "revision": applied.get("revision"),
            }
    content = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
    snapshot = hashlib.sha256(content).hexdigest()
    if data.get("preview") is True:
        return jsonify(success=True, report_text=content.decode("utf-8"), snapshot=snapshot)
    if "snapshot" in data and data["snapshot"] != snapshot:
        return jsonify({"error": "La revisión ha cambiado. Vuelva a comprobar el informe antes de guardarlo."}), 409

    log_audit("export", f"DOC={document_id} FINDINGS={len(findings)}")
    prune_stale_export_reports()
    workspace = _workspace_dir()
    export_path = safe_join(workspace, f"{document_id}_pii_report.json")
    if export_path is None:
        return jsonify({"error": "Ruta de exportación no válida."}), 400
    # Los lectores ven el informe anterior o el nuevo, incluso si el guardado falla.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=workspace, suffix=".tmp", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(content)
        os.replace(tmp_path, export_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return jsonify(success=True, envelope=envelope)


@app.route("/api/session/apply-original", methods=["POST"])
def apply_original_redactions():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Petición inválida."}), 400

    session_id = _sanitize_id(data.get("session_id"))
    findings = _clean_findings(data.get("findings", []))
    if not session_id:
        return jsonify({"error": "No hay sesión visual activa para aplicar la edición sobre el original."}), 400
    if findings is None:
        return jsonify({"error": "Formato de hallazgos no válido."}), 400

    session_dir = _existing_session_dir(session_id)
    if session_dir is None:
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
    session_dir = _existing_session_dir(safe_id)
    if session_dir is None:
        return jsonify({"error": "La sesión visual ya no existe o ha caducado."}), 404
    try:
        applied = load_applied_metadata(session_dir)
    except Exception:
        return jsonify({"error": "No existe todavía una versión editada del original en esta sesión."}), 404

    if "issues" not in applied:
        return jsonify(error="Vuelva a aplicar el testado con la versión actual."), 409
    if request.args.get("revision", applied.get("revision")) != applied.get("revision"):
        return jsonify(error="La copia ha cambiado. Vuelva a revisar las páginas."), 409
    return _send_applied_pdf(session_dir, "copia_testada.pdf", applied, request.args.get("draft") == "1")


def _send_applied_pdf(directory, name, applied, allow_draft):
    try:
        revision = uuid.UUID(hex=applied["revision"]).hex
    except (KeyError, TypeError, ValueError, AttributeError):
        return jsonify(error="Vuelva a aplicar el testado para regenerar la copia."), 409
    path = os.path.join(directory, f"{revision}_testado.pdf")
    if os.path.islink(path) or not os.path.isfile(path):
        return jsonify(error="La copia ya no está disponible."), 404
    return _send_reviewed_pdf(path, name, applied, allow_draft)


def _send_reviewed_pdf(path, name, stats, allow_draft):
    issues = stats["issues"]
    if issues and not allow_draft:
        return jsonify(error="La copia requiere revisión.", draft_available=True, issues=issues), 409
    with open(path, "rb") as handle:
        response = send_file(io.BytesIO(handle.read()), mimetype="application/pdf", as_attachment=True,
                             download_name=("BORRADOR_" if issues else "") + name)
    response.headers["X-Velo-Estado"] = "borrador" if issues else "testado"
    for key, header in (("unprojected", "X-Velo-Sin-Proyectar"), ("partial", "X-Velo-Proyeccion-Parcial")):
        response.headers[header] = ",".join(_sanitize_id(i) for i in stats["projection"][key])[:2000]
    return response


@app.route("/api/export/redacted-pdf", methods=["POST"])
def export_redacted_pdf():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Petición inválida."}), 400

    session_id = _sanitize_id(data.get("session_id"))
    findings = _clean_findings(data.get("findings", []))
    document_id = _sanitize_id(data.get("document_id", f"DOC-{uuid.uuid4().hex[:8].upper()}"))
    if not session_id:
        return jsonify({"error": "No hay sesión visual activa para exportar el PDF original."}), 400
    if findings is None:
        return jsonify({"error": "Formato de hallazgos no válido."}), 400

    session_dir = _existing_session_dir(session_id)
    if session_dir is None:
        return jsonify({"error": "La sesión visual ya no existe o ha caducado."}), 404

    # Dos modos de exportación (v0.5.0):
    #   - "image" (por defecto, comportamiento histórico): copia rasterizada
    #     por página con las máscaras pintadas. Inmune a errores de capa de
    #     texto, pero pierde la capa textual y pesa más.
    #   - "native": expurgo real con apply_redactions de PyMuPDF. El texto
    #     subyacente se ELIMINA del fichero (no solo se tapa) y el PDF
    #     resultante conserva su naturaleza vectorial y su capa de texto.
    redaction_mode = str(data.get("redaction_mode") or "image").strip().lower()
    if redaction_mode not in ("image", "native"):
        return jsonify({"error": "Modo de redacción no válido. Use 'image' o 'native'."}), 400

    suffix = "native_redacted" if redaction_mode == "native" else "visual_redacted"
    output_name = f"{document_id or 'DOC'}_{suffix}.pdf"
    allow_draft = data.get("draft") is True
    try:
        if redaction_mode == "image":
            stats = apply_redactions_to_original(session_dir, session_id, findings)
            return _send_applied_pdf(session_dir, output_name, stats, allow_draft)
        with tempfile.TemporaryDirectory(dir=session_dir) as output_dir:
            path = os.path.join(output_dir, "copia.pdf")
            stats = export_native_redacted_pdf(session_dir, findings, path)
            log_audit("export_native_pdf", f"DOC={document_id} RECT={stats['total_rectangles']} INCIDENCIAS={len(stats['issues'])}")
            return _send_reviewed_pdf(path, output_name, stats, allow_draft)
    except Exception:
        logger.exception("No se pudo completar el testado del PDF (modo=%s)", redaction_mode)
        return jsonify(error="No se pudo completar el testado y saneado de la copia. Revise el original o utilice la copia visual."), 400


@app.route("/api/session/<session_id>/asset/<filename>")
def serve_session_asset(session_id, filename):
    safe_id = _sanitize_id(session_id)
    safe_file = os.path.basename(filename)
    if not safe_id:
        return jsonify({"error": "Sesión inválida."}), 400

    session_dir = _existing_session_dir(safe_id)
    if session_dir is None:
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
                "modes": {
                    "image": bool(visual.get("fitz") and visual.get("pillow")),
                    "native": bool(visual.get("native_redaction")),
                },
                "note": "La revisión visual de PDF usa la imagen original por página y coordina los tachados con la base textual/OCR de esa misma sesión. El modo 'native' elimina realmente el texto subyacente (testado de la copia PDF) en lugar de taparlo.",
            },
        }
    )


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    import threading

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
                "Error no fatal al limpiar sesiones durante el apagado: %s",
                exc,
                exc_info=True,
            )
        time.sleep(0.5)
        # Antes se enviaba SIGINT al propio proceso. En Windows os.kill(pid,
        # SIGINT) equivale a TerminateProcess con código 2 (el instalador
        # mostraba «Velo terminó con código 2») y, lanzado en segundo plano,
        # el proceso hereda SIGINT ignorado y no se apagaba. Se sale de forma
        # explícita tras limpiar y vaciar los logs.
        logger.info("Velo apagado desde la interfaz")
        logging.shutdown()
        os._exit(0)

    threading.Thread(target=_shutdown_later, daemon=True).start()
    return jsonify({"success": True, "message": "Apagando Velo..."})
