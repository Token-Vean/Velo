"""Regresiones PDF de la auditoría de noviembre de 2026 (requieren PyMuPDF).

En CI se instala requirements-visual.txt, así que estas pruebas se ejecutan
allí aunque en un entorno sin PyMuPDF se omitan.
"""

from __future__ import annotations

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
