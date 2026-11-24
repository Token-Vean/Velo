"""Regresiones PDF de la auditoría de noviembre de 2026 (requieren PyMuPDF).

En CI se instala requirements-visual.txt, así que estas pruebas se ejecutan
allí aunque en un entorno sin PyMuPDF se omitan.
"""

from __future__ import annotations

from collections import defaultdict
import io
import re

import pytest

pymupdf = pytest.importorskip("pymupdf")

from velo_engine import visual as visual_module  # noqa: E402


def _pdf_con_extras(ruta):
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), "Interesado Victor Villapalos")
    pagina.add_text_annot((72, 120), "Nota interna: DNI 12345678Z")
    documento.embfile_add("adjunto.txt", b"Adjunto con 87654321X")
    documento.set_toc([[1, "Expediente de Victor Villapalos", 1]])
    documento.set_metadata({"author": "Autor sensible", "title": "Expediente Villapalos"})
    documento.save(ruta)
    documento.close()


def test_expurgo_nativo_sanea_anotaciones_adjuntos_e_indice(tmp_path):
    ruta = tmp_path / "original.pdf"
    _pdf_con_extras(ruta)
    texto, _fmt, error, _meta = visual_module.read_pdf_for_visual_review(str(ruta), str(tmp_path), "s1")
    assert error is None
    inicio = texto.index("Victor")
    findings = [{
        "id": "f001", "status": "confirmed", "text": "Victor Villapalos",
        "position": {"start": inicio, "end": inicio + len("Victor Villapalos")},
    }]
    salida = tmp_path / "nativo.pdf"
    stats = visual_module.export_native_redacted_pdf(str(tmp_path), findings, str(salida))

    assert stats["sanitized"]["scrubbed"] is True
    assert stats["sanitized"]["annotations_removed"] >= 1
    assert stats["projection"] == {"unprojected": [], "partial": []}

    resultado = pymupdf.open(salida)
    try:
        assert "Villapalos" not in "".join(p.get_text() for p in resultado)
        assert list(resultado[0].annots()) == []
        assert resultado.embfile_count() == 0
        assert resultado.get_toc() == []
        assert not any(resultado.metadata.get(k) for k in ("author", "title", "subject", "keywords"))
    finally:
        resultado.close()
    bruto = salida.read_bytes()
    assert b"12345678Z" not in bruto and b"87654321X" not in bruto


def test_hallazgo_sin_coordenadas_se_informa(tmp_path):
    ruta = tmp_path / "original.pdf"
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), "Interesado Victor Villapalos")
    documento.save(ruta)
    documento.close()
    texto, _fmt, error, _meta = visual_module.read_pdf_for_visual_review(str(ruta), str(tmp_path), "s2")
    assert error is None
    inicio = texto.index("Victor")
    findings = [
        {"id": "f001", "status": "confirmed", "text": "Victor",
         "position": {"start": inicio, "end": inicio + 6}},
        {"id": "f002", "status": "confirmed", "text": "fantasma",
         "position": {"start": len(texto) + 100, "end": len(texto) + 108}},
    ]
    stats = visual_module.export_native_redacted_pdf(str(tmp_path), findings, str(tmp_path / "n.pdf"))
    assert stats["projection"]["unprojected"] == ["f002"]
    aplicado = visual_module.apply_redactions_to_original(str(tmp_path), "s2", findings)
    assert aplicado["projection"]["unprojected"] == ["f002"]


def test_pagina_gigante_limita_la_escala(tmp_path):
    ruta = tmp_path / "original.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page(width=14_000, height=14_000)
    pagina.insert_text((72, 72), "Texto en pagina enorme 12345678Z", fontsize=40)
    documento.save(ruta)
    documento.close()
    texto, _fmt, error, meta = visual_module.read_pdf_for_visual_review(str(ruta), str(tmp_path), "s3")
    assert error is None
    pagina_meta = meta["pages"][0]
    assert pagina_meta["width"] * pagina_meta["height"] <= visual_module.MAX_RENDER_PIXELS * 1.01
    assert pagina_meta["scale"] < visual_module.TEXT_RENDER_SCALE

    inicio = texto.index("12345678Z")
    findings = [{"id": "f001", "status": "confirmed", "text": "12345678Z",
                 "position": {"start": inicio, "end": inicio + 9}}]
    salida = tmp_path / "gigante_nativo.pdf"
    visual_module.export_native_redacted_pdf(str(tmp_path), findings, str(salida))
    resultado = pymupdf.open(salida)
    try:
        assert "12345678Z" not in resultado[0].get_text()
        assert "enorme" in resultado[0].get_text()
    finally:
        resultado.close()


def test_proyeccion_exige_cada_caracter_no_blanco():
    pages = [{"words": [{"start": 0, "end": 10}, {"start": 0, "end": 10}]}]
    finding = {"id": "f1", "position": {"start": 0, "end": 11}, "text": "ABCDEFGHIJK"}
    assert visual_module.projection_report(pages, [finding])["partial"] == ["f1"]


def test_copia_con_formulario_y_pagina_rotada(tmp_path):
    path = tmp_path / "original.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 90), "ALFA BETA")
        for i in range(2):
            widget = pymupdf.Widget()
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.field_name = f"Campo{i}"
            widget.field_value = "Valor de ejemplo"
            widget.rect = pymupdf.Rect(60, 125 + 30*i, 260, 145 + 30*i)
            annot = page.add_widget(widget)
            doc.xref_set_key(annot.xref, "DV", "(Inicial)")
        page.set_rotation(90)
        doc.save(path)
    text, _, error, meta = visual_module.read_pdf_for_visual_review(str(path), str(tmp_path), "s")
    assert not error
    start = text.index("ALFA")
    found = [{"id": "f1", "status": "confirmed", "text": "ALFA", "position": {"start": start, "end": start+4}}]
    output = tmp_path / "copia.pdf"
    visual_module.export_native_redacted_pdf(str(tmp_path), found, str(output))
    with pymupdf.open(output) as doc:
        assert list(doc[0].widgets()) == []
        assert doc.xref_get_key(doc.pdf_catalog(), "AcroForm")[0] == "null"
        assert "ALFA" not in doc[0].get_text() and "BETA" in doc[0].get_text()
    applied = visual_module.apply_redactions_to_original(str(tmp_path), "s", found)
    from PIL import Image
    word = next(w for w in meta["pages"][0]["words"] if w["text"] == "ALFA")
    box = word["bbox"]
    with Image.open(tmp_path / "assets" / applied["pages"][0]["image_url"].split("/")[-1]) as image:
        assert image.getpixel((int((box[0]+box[2])/2), int((box[1]+box[3])/2))) == (0, 0, 0)


def test_entrega_borrador_y_fallo_saneado(tmp_path, monkeypatch):
    from velo_engine.app import app
    from velo_engine import security
    from PIL import Image

    monkeypatch.setitem(app.config, "WORKSPACE", str(tmp_path))
    monkeypatch.setattr(security._limiter, "_hits", defaultdict(list))
    session_dir = tmp_path / "sessions" / "prueba"
    session_dir.mkdir(parents=True)
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 90), "ALFA BETA")
        img = io.BytesIO()
        Image.new("RGB", (25, 25), "blue").save(img, "PNG")
        page.insert_image(pymupdf.Rect(30, 140, 80, 190), stream=img.getvalue())
        doc.save(session_dir / "original.pdf")
    text, _, error, meta = visual_module.read_pdf_for_visual_review(str(session_dir / "original.pdf"), str(session_dir), "prueba")
    assert not error and "imágenes" in meta["pages"][0]["coverage_note"]
    start = text.index("ALFA")
    payload = {"session_id": "prueba", "findings": [{"id": "f1", "status": "confirmed", "text": "ALFA",
                "position": {"start": start, "end": start+4}}]}
    with app.test_client() as client:
        token = re.search(r'name="csrf-token" content="([^"]+)', client.get("/").get_data(as_text=True)).group(1)
        headers = {"Host": "localhost:7780", "Origin": "http://localhost:7780", "X-CSRF-Token": token}
        for mode in ("image", "native"):
            request = {**payload, "redaction_mode": mode}
            warn = client.post("/api/export/redacted-pdf", json=request, headers=headers)
            assert warn.status_code == 409 and warn.json["draft_available"]
            assert "Página 1" in warn.json["issues"][0]
            draft = client.post("/api/export/redacted-pdf", json={**request, "draft": True}, headers=headers)
            assert draft.status_code == 200 and "BORRADOR_" in draft.headers["Content-Disposition"]
        url = "/api/session/prueba/applied-original-pdf"
        assert client.get(url, headers=headers).status_code == 409
        assert client.get(url + "?draft=1", headers=headers).headers["X-Velo-Estado"] == "borrador"

        def unavailable(*args, **kwargs):
            raise RuntimeError("Saneado no disponible")
        monkeypatch.setattr(pymupdf.Document, "scrub", unavailable)
        blocked = client.post("/api/export/redacted-pdf", json={**payload, "redaction_mode": "native", "draft": True}, headers=headers)
        assert blocked.status_code == 400 and blocked.is_json
