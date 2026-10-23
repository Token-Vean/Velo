"""Endurecimiento web: validación de Host (DNS rebinding) y CSP sin scripts inline."""

from __future__ import annotations

import re

import pytest

from velo_engine.app import app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize("host", ["localhost", "localhost:7780", "127.0.0.1:7780", "[::1]:7780"])
def test_host_local_aceptado(client, host):
    response = client.get("/api/status", headers={"Host": host})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    ["evil.example", "evil.example:7780", "127.0.0.1.nip.io:7780", "localhost:7780/x?", "user@localhost"],
)
def test_host_ajeno_rechazado(client, host):
    response = client.get("/api/status", headers={"Host": host})
    assert response.status_code == 421


def test_host_extra_configurable(client):
    app.config["ALLOWED_HOSTS"] = ["velo.intranet"]
    try:
        assert client.get("/api/status", headers={"Host": "velo.intranet"}).status_code == 200
    finally:
        app.config.pop("ALLOWED_HOSTS", None)


def test_csp_no_permite_scripts_inline(client):
    response = client.get("/", headers={"Host": "localhost:7780"})
    csp = response.headers["Content-Security-Policy"]
    script_src = re.search(r"script-src ([^;]+)", csp).group(1)
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src


def test_pagina_sin_codigo_inline(client):
    html = client.get("/", headers={"Host": "localhost:7780"}).get_data(as_text=True)
    # Ningún <script> con cuerpo y ningún manejador on*="..."
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert not re.search(r"\son[a-z]+\s*=", html)
    assert "/static/app.js" in html


def test_app_js_servido(client):
    response = client.get("/static/app.js", headers={"Host": "localhost:7780"})
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "CLICK_ACTIONS" in body and "escapeAttr" in body
