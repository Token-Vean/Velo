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
  3. El wheel del mismo modelo en Hugging Face (repositorio spacy/<modelo>),
     publicado por Explosion por un canal distinto. Es otra compilación del
     wheel (otro nombre y otro hash global), así que se compara el contenido:
     el SHA-256 de cada fichero del modelo según el RECORD de ambos wheels.

Falla si alguna fuente contradice el lock o si ninguna fuente independiente
(2 o 3) lo confirma. Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
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


def _contenido_modelo(wheel: bytes) -> dict[str, str]:
    """{ruta relativa: sha256} de los ficheros del modelo según RECORD.

    Se excluye *.dist-info (metadatos del empaquetado, que difieren entre
    compilaciones) y se comprueba que cada fichero coincide con su RECORD.
    """
    resultado: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(wheel)) as zf:
        record = next(n for n in zf.namelist() if n.endswith(".dist-info/RECORD"))
        filas = csv.reader(io.StringIO(zf.read(record).decode("utf-8")))
        for fila in filas:
            if len(fila) < 2 or not fila[1] or ".dist-info/" in fila[0]:
                continue
            algoritmo, _, valor = fila[1].partition("=")
            if algoritmo != "sha256":
                continue
            real = base64.urlsafe_b64encode(hashlib.sha256(zf.read(fila[0])).digest()).rstrip(b"=").decode()
            if real != valor:
                raise ValueError(f"RECORD no coincide con el contenido de {fila[0]}")
            resultado[fila[0]] = valor
    return resultado


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

    wheel_github = _get(url)
    descargado = hashlib.sha256(wheel_github).hexdigest()
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
        arbol = json.loads(_get(f"https://huggingface.co/api/models/spacy/{nombre}/tree/main"))
        ruedas = [e["path"] for e in arbol if str(e.get("path", "")).endswith(".whl")]
        if not ruedas:
            raise LookupError("sin wheels en el repositorio")
        contenido_github = _contenido_modelo(wheel_github)
        wheel_hf = _get(f"https://huggingface.co/spacy/{nombre}/resolve/main/{ruedas[0]}")
        contenido_hf = _contenido_modelo(wheel_hf)
        print(
            f"[3] Hugging Face spacy/{nombre}/{ruedas[0]}: "
            f"{len(contenido_hf)} ficheros; GitHub: {len(contenido_github)} ficheros"
        )
        if contenido_github and contenido_github == contenido_hf:
            confirmaciones.append(
                f"Hugging Face (los {len(contenido_hf)} ficheros del modelo son idénticos byte a byte)"
            )
        else:
            solo_gh = sorted(set(contenido_github.items()) - set(contenido_hf.items()))
            solo_hf = sorted(set(contenido_hf.items()) - set(contenido_github.items()))
            for ruta, valor in solo_gh[:10]:
                print(f"      distinto/ausente en HF: {ruta} {valor}")
            for ruta, valor in solo_hf[:10]:
                print(f"      distinto/ausente en GitHub: {ruta} {valor}")
            fallos.append("el contenido del modelo difiere entre GitHub y Hugging Face")
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
