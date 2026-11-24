"""Regresiones de la auditoría de seguridad y privacidad de noviembre de 2026."""

from __future__ import annotations

import io
import json
import os
import re
import time

import pytest

from velo_engine import security
from velo_engine.app import app, prune_orphan_uploads
from velo_engine.detector import detect_regex

HOST = {"Host": "localhost:7780"}


@pytest.fixture(autouse=True)
def _sin_rate_limit():
    security._limiter._hits.clear()
    yield
    security._limiter._hits.clear()


@pytest.fixture()
def client(tmp_path):
    previo = app.config.get("WORKSPACE")
    app.config["TESTING"] = True
    app.config["WORKSPACE"] = str(tmp_path)
    with app.test_client() as test_client:
        yield test_client
    app.config["WORKSPACE"] = previo


def _token(client) -> str:
    pagina = client.get("/", headers=HOST).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', pagina).group(1)


def _post_json(client, url, payload, **extra_headers):
    headers = {**HOST, "Origin": "http://localhost:7780", "X-CSRF-Token": _token(client), **extra_headers}
    return client.post(url, data=json.dumps(payload), headers=headers, content_type="application/json")


# ---------------------------------------------------------------------------
# Detector: ReDoS y coste cuadrático
# ---------------------------------------------------------------------------

def test_regex_email_lineal_con_texto_hostil():
    # Con el patrón anterior, 40 000 caracteres tardaban ~1,5 s y el tiempo
    # crecía de forma cuadrática (2 M caracteres -> horas).
    texto = "a." * 200_000
    inicio = time.perf_counter()
    detect_regex(texto)
    assert time.perf_counter() - inicio < 3


def test_email_sigue_detectandose():
    hallazgos = detect_regex("Escriba a nombre.apellido+expte@ayto-ejemplo.es hoy.")
    assert [(h["type"], h["text"]) for h in hallazgos] == [("email", "nombre.apellido+expte@ayto-ejemplo.es")]


def test_muchos_hallazgos_no_es_cuadratico():
    texto = "a@b.cc " * 60_000
    inicio = time.perf_counter()
    hallazgos = detect_regex(texto)
    assert len(hallazgos) == 60_000
    assert time.perf_counter() - inicio < 5


def test_demasiados_hallazgos_se_rechazan(client, monkeypatch):
    import velo_engine.app as app_module

    monkeypatch.setattr(app_module, "MAX_FINDINGS", 5)
    respuesta = _post_json(client, "/api/analyze/text", {"text": "a@b.cc " * 10})
    assert respuesta.status_code == 400
    assert "Divídalo" in respuesta.get_json()["error"]


# ---------------------------------------------------------------------------
# Validación de hallazgos enviados por el navegador
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "findings",
    [
        "no-es-lista",
        [1, 2, 3],
        [{"id": "f1", "status": "confirmed", "position": "0-3"}],
        [{"id": "f1", "status": "confirmed", "position": {"start": "0", "end": 3}}],
        [{"id": "f1", "status": "confirmed", "position": {"start": 5, "end": 2}}],
        [{"id": "f1", "status": "otro", "position": {"start": 0, "end": 2}}],
    ],
)
def test_export_rechaza_hallazgos_mal_formados(client, findings):
    respuesta = _post_json(client, "/api/export", {"document_id": "DOC-T", "findings": findings})
    assert respuesta.status_code == 400


def test_export_acepta_hallazgos_validos(client):
    findings = [{
        "id": "f001", "text": "12345678Z", "category": "identification", "type": "dni",
        "label": "DNI", "position": {"start": 0, "end": 9}, "confidence": 1.0,
        "method": "regex", "status": "confirmed",
    }]
    respuesta = _post_json(client, "/api/export", {"document_id": "DOC-T", "findings": findings})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["envelope"]["summary"]["confirmed"] == 1


# ---------------------------------------------------------------------------
# DOCX: tablas, encabezados, pies y comentarios
# ---------------------------------------------------------------------------

docx = pytest.importorskip("docx")


def _docx_completo(path):
    documento = docx.Document()
    documento.add_paragraph("Cuerpo sin datos.")
    tabla = documento.add_table(rows=1, cols=2)
    tabla.cell(0, 0).text = "DNI"
    tabla.cell(0, 1).text = "12345678Z"
    documento.sections[0].header.paragraphs[0].text = "Encabezado ana@example.org"
    documento.sections[0].footer.paragraphs[0].text = "Pie X-1234567-L"
    parrafo = documento.add_paragraph("Texto comentado")
    if hasattr(documento, "add_comment"):
        documento.add_comment(parrafo.runs, text="Comentario 87654321X", author="Autora")
    documento.save(path)


def test_docx_lee_tablas_encabezados_pies_y_comentarios(tmp_path):
    from velo_engine.reader import read_file

    ruta = tmp_path / "completo.docx"
    _docx_completo(ruta)
    texto, formato, error = read_file(str(ruta))
    assert error is None and formato == "docx"
    tipos = {(h["type"], h["text"]) for h in detect_regex(texto)}
    assert ("dni", "12345678Z") in tipos          # tabla
    assert ("email", "ana@example.org") in tipos  # encabezado
    assert ("nie", "X-1234567-L") in tipos        # pie
    if hasattr(docx.Document(), "add_comment"):
        assert ("dni", "87654321X") in tipos      # comentario


def test_docx_avisos_en_la_respuesta(client, tmp_path):
    ruta = tmp_path / "avisos.docx"
    _docx_completo(ruta)
    headers = {**HOST, "Origin": "http://localhost:7780", "X-CSRF-Token": _token(client)}
    respuesta = client.post(
        "/api/analyze/file",
        data={"file": (io.BytesIO(ruta.read_bytes()), "Expediente_Ñúñez.docx")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200, respuesta.get_json()
    datos = respuesta.get_json()
    assert isinstance(datos["extraction_notes"], list)
    # La subida temporal no queda en el workspace.
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".docx") and n != "avisos.docx"]


def test_nombre_no_ascii_conserva_extension(client):
    headers = {**HOST, "Origin": "http://localhost:7780", "X-CSRF-Token": _token(client)}
    respuesta = client.post(
        "/api/analyze/file",
        data={"file": (io.BytesIO("DNI 12345678Z".encode()), "数据.txt")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200, respuesta.get_json()


# ---------------------------------------------------------------------------
# Temporales, logs y cabeceras
# ---------------------------------------------------------------------------

def test_purga_subidas_huerfanas(tmp_path):
    app.config["WORKSPACE"] = str(tmp_path)
    huerfana = tmp_path / "0123456789ab.pdf"
    ajena = tmp_path / "mis_notas.pdf"
    antiguo = time.time() - 60  # la resolución del mtime en Windows es gruesa
    for ruta in (huerfana, ajena):
        ruta.write_bytes(b"%PDF-1.4")
        os.utime(ruta, (antiguo, antiguo))
    assert prune_orphan_uploads(max_age_seconds=0) == 1
    assert not huerfana.exists() and ajena.exists()


def test_hash_de_auditoria_no_es_sha256_plano(client):
    import hashlib

    with app.test_request_context("/", headers=HOST):
        valor = security.hash_text("12345678Z")
    assert valor != hashlib.sha256(b"12345678Z").hexdigest()[:16]
    assert len(valor) == 16


def test_log_de_auditoria_se_redirige(tmp_path):
    destino = tmp_path / "logs"
    security.setup_audit_log(str(destino))
    rutas = [getattr(h, "baseFilename", "") for h in security._audit.handlers]
    assert rutas == [str(destino / "velo_audit.log")]


def test_same_site_sin_origin_se_rechaza(client):
    token = _token(client)
    respuesta = client.post(
        "/api/analyze/text",
        data=json.dumps({"text": "hola"}),
        headers={**HOST, "Sec-Fetch-Site": "same-site", "X-CSRF-Token": token},
        content_type="application/json",
    )
    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# Inyección en logs (CodeQL py/log-injection)
# ---------------------------------------------------------------------------

def test_para_log_neutraliza_saltos_y_controles():
    valor = security.para_log("/x\n2026-11-24 | INFO | linea falsa\r\x1b[31m")
    assert "\n" not in valor and "\r" not in valor and "\x1b" not in valor
    assert "\\n" in valor


def test_ruta_con_salto_de_linea_no_falsifica_el_log(client, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        respuesta = client.post(
            "/api/x%0A2026-11-24 00:00:00 | INFO | velo | linea falsa",
            headers={"Host": "localhost:7780", "Origin": "http://evil.example"},
        )
    assert respuesta.status_code == 403
    registros = [r.getMessage() for r in caplog.records if "same-origin" in r.getMessage()]
    assert registros and all("\n" not in m for m in registros)


def test_informe_previsualizado_es_el_guardado(client, tmp_path):
    payload = {
        "document_id": "DOC-AULA", "analysis_date": "2026-11-24T09:00:00.000Z",
        "source_format": "docx", "extraction_notes": ["Cabecera con imagen"],
        "risk_reviewed": True, "risk_assessment_note": "Revisados cargo y fecha", "findings": [],
    }
    preview = _post_json(client, "/api/export", {**payload, "preview": True}).get_json()
    path = tmp_path / "DOC-AULA_pii_report.json"
    assert not path.exists()
    result = _post_json(client, "/api/export", {**payload, "snapshot": preview["snapshot"]})
    assert result.status_code == 200
    assert path.read_text(encoding="utf-8") == preview["report_text"]
    envelope = result.get_json()["envelope"]
    assert envelope == json.loads(preview["report_text"])
    assert envelope["audit"]["residual_risk_note"] == "Revisados cargo y fecha"
    assert envelope["audit"]["residual_risk_reviewed"]
    assert envelope["extraction_notes"] == ["Cabecera con imagen"]
    changed = _post_json(client, "/api/export", {**payload, "risk_reviewed": False, "snapshot": preview["snapshot"]})
    assert changed.status_code == 409
    assert path.read_text(encoding="utf-8") == preview["report_text"]


def test_imagen_en_cabecera_word(tmp_path):
    from PIL import Image
    from velo_engine.reader import docx_review_notes

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buffer, "PNG")
    buffer.seek(0)
    doc = docx.Document()
    doc.add_paragraph("Solicitud de prueba")
    doc.sections[0].header.paragraphs[0].add_run().add_picture(buffer)
    path = tmp_path / "solicitud.docx"
    doc.save(path)
    assert any("cabecera" in note and "imágenes" in note for note in docx_review_notes(str(path)))
