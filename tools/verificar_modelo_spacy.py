#!/usr/bin/env python3
"""Contrasta el hash del modelo spaCy fijado en el lock con fuentes independientes.

El lock (locks/requirements-nlp.lock) fija el SHA-256 del wheel del modelo
es_core_news_md. pip comprueba al instalar que el fichero descargado coincide
con ese hash, pero el hash se calculó a partir de la misma descarga: si la
publicación hubiera sido manipulada antes de generar el lock, pip la daría por
buena. Este script lo contrasta con:

  1. La descarga actual del wheel (el hash del lock sigue sirviendo).
  2. El digest SHA-256 que GitHub calcula y publica para cada fichero de una
     release (API de releases de explosion/spacy-models).
  3. El SHA-256 del mismo modelo en Hugging Face (repositorio spacy/<modelo>),
     publicado por Explosion por un canal distinto.

Falla si alguna fuente contradice el lock o si ninguna fuente independiente
(2 o 3) lo confirma. Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "locks" / "requirements-nlp.lock"
PATRON_URL = re.compile(
    r"^(?P<nombre>es[-_]core[-_]news[-_][a-z]+) @ (?P<url>https://github\.com/explosion/spacy-models/"
    r"releases/download/(?P<tag>[^/]+)/(?P<fichero>[^\s]+\.whl))"
)


def _get(url: str, *, json_api: bool = False) -> bytes:
    cabeceras = {"User-Agent": "velo-verificacion-modelo"}
    token = os.environ.get("GITHUB_TOKEN")
    if json_api and token and url.startswith("https://api.github.com/"):
        cabeceras["Authorization"] = f"Bearer {token}"
    peticion = urllib.request.Request(url, headers=cabeceras)
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:  # noqa: S310 (URL fija https)
        return respuesta.read()


def _leer_lock() -> tuple[str, str, str, str, set[str]]:
    lineas = LOCK.read_text(encoding="utf-8").splitlines()
    for indice, linea in enumerate(lineas):
        coincidencia = PATRON_URL.match(linea.strip())
        if not coincidencia:
            continue
        hashes = set()
        for siguiente in lineas[indice:]:
            hashes.update(re.findall(r"--hash=sha256:([0-9a-f]{64})", siguiente))
            if siguiente is not linea and not siguiente.startswith(" "):
                break
        return (
            coincidencia["nombre"].replace("-", "_"), coincidencia["url"], coincidencia["tag"],
            coincidencia["fichero"], hashes,
        )
    sys.exit(f"[ERROR] No se encontró el modelo spaCy con URL de GitHub en {LOCK}")


def main() -> int:
    nombre, url, tag, fichero, hashes_lock = _leer_lock()
    if len(hashes_lock) != 1:
        print(f"[ERROR] Se esperaba un único hash para {nombre}; hay {len(hashes_lock)}")
        return 1
    hash_lock = next(iter(hashes_lock))
    print(f"Modelo: {nombre} ({tag})\nLock:   sha256:{hash_lock}")

    fallos: list[str] = []
    confirmaciones: list[str] = []

    descargado = hashlib.sha256(_get(url)).hexdigest()
    print(f"[1] Descarga actual:        sha256:{descargado}")
    if descargado != hash_lock:
        fallos.append("la descarga actual no coincide con el lock")

    try:
        release = json.loads(_get(
            f"https://api.github.com/repos/explosion/spacy-models/releases/tags/{tag}", json_api=True,
        ))
        digest = next(
            (a.get("digest") for a in release.get("assets", []) if a.get("name") == fichero), None,
        )
        print(f"[2] Digest de GitHub:       {digest}")
        if digest:
            if digest.lower() == f"sha256:{hash_lock}":
                confirmaciones.append("digest de la release en GitHub")
            else:
                fallos.append("el digest publicado por GitHub no coincide")
    except Exception as exc:  # noqa: BLE001
        print(f"[2] Digest de GitHub:       no disponible ({type(exc).__name__}: {exc})")

    try:
        version = tag.rsplit("-", 1)[-1]
        arbol = json.loads(_get(f"https://huggingface.co/api/models/spacy/{nombre}/tree/main"))
        ruedas = [e for e in arbol if str(e.get("path", "")).endswith(".whl") and e.get("lfs")]
        print(f"[3] Hugging Face spacy/{nombre} (versión esperada {version}):")
        for entrada in ruedas:
            oid = entrada["lfs"].get("oid") or entrada["lfs"].get("sha256")
            print(f"      {entrada['path']}: sha256:{oid}")
            if oid == hash_lock:
                confirmaciones.append(f"Hugging Face ({entrada['path']})")
        if ruedas and not any((e["lfs"].get("oid") or e["lfs"].get("sha256")) == hash_lock for e in ruedas):
            # Hugging Face puede alojar otra compilación del modelo: se informa
            # sin tratarlo como contradicción si GitHub ya lo confirma.
            print("      (ningún wheel coincide con el lock)")
    except Exception as exc:  # noqa: BLE001
        print(f"[3] Hugging Face:           no disponible ({type(exc).__name__}: {exc})")

    if fallos:
        print("[ERROR] " + "; ".join(fallos))
        return 1
    if not confirmaciones:
        print("[ERROR] Ninguna fuente independiente confirma el hash del lock.")
        return 1
    print("[OK] Hash confirmado por: " + ", ".join(confirmaciones))
    return 0


if __name__ == "__main__":
    sys.exit(main())
