"""Tests de las novedades de la versión 0.5.0."""

from __future__ import annotations

import json
import os
import time

import pytest

from velo_engine.detector import _valid_nss, detect_regex


# ---------------------------------------------------------------------------
# Validación de dígitos de control del NSS
# ---------------------------------------------------------------------------

def _nss_valido() -> str:
    base = 2812345678
    return f"28/12345678/{base % 97:02d}"


def test_nss_valido_pasa():
    assert _valid_nss(_nss_valido()) is True


def test_nss_control_incorrecto_se_rechaza():
    base = 2812345678
    control_malo = (base % 97 + 1) % 100
    assert _valid_nss(f"28/12345678/{control_malo:02d}") is False


def test_nss_longitud_no_canonica_se_acepta():
    # Con longitudes distintas de 12 dígitos no se puede validar el control;
    # se acepta para no descartar posibles verdaderos positivos.
    assert _valid_nss("28/1234567/89") is True


def test_detector_filtra_nss_invalido():
    valido = _nss_valido().replace("/", "-")
    texto = f"NSS {valido} y expediente 28-11111111-99."
    tipos = [(h["type"], h["text"]) for h in detect_regex(texto) if h["type"] == "nss"]
    assert (("nss", valido)) in tipos
    assert all(t[1] != "28-11111111-99" for t in tipos)


# ---------------------------------------------------------------------------
# Contención de rutas (_is_within) y purga de informes
# ---------------------------------------------------------------------------

flask = pytest.importorskip("flask")

from velo_engine.app import _is_within, app, prune_stale_export_reports  # noqa: E402


def test_is_within_rechaza_prefijo_trampa(tmp_path):
    root = tmp_path / "workspace"
    trampa = tmp_path / "workspace-otro" / "x"
    assert _is_within(str(root), str(trampa)) is False


def test_is_within_acepta_subruta(tmp_path):
    root = tmp_path / "workspace"
    dentro = root / "sessions" / "abc"
    assert _is_within(str(root), str(dentro)) is True


def test_prune_export_reports(tmp_path):
    app.config["WORKSPACE"] = str(tmp_path)

    viejo = tmp_path / "DOC-VIEJO_pii_report.json"
    nuevo = tmp_path / "DOC-NUEVO_pii_report.json"
    otro = tmp_path / "no_me_toques.txt"
    for path in (viejo, nuevo, otro):
        path.write_text(json.dumps({}), encoding="utf-8")

    antiguo = time.time() - 48 * 3600
    os.utime(viejo, (antiguo, antiguo))

    removed = prune_stale_export_reports(ttl_hours=24)

    assert removed == 1
    assert not viejo.exists()
    assert nuevo.exists()
    assert otro.exists()
