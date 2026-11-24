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
  3. Los paquetes del mismo modelo y versión que conda-forge y el canal
     «main» de Anaconda construyeron por su cuenta (diciembre de 2024 para la
     3.8.0). Son otros empaquetados (otro hash global), así que se compara el
     contenido: el SHA-256 de cada fichero del modelo.
  4. Hugging Face (spacy/<modelo>), si aloja esa misma versión.

Falla si alguna fuente que tenga la misma versión contradice el lock, o si
ninguna fuente independiente (2, 3 o 4) lo confirma. Usa la biblioteca
estándar y, para paquetes .conda, el programa `zstd`.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


def _b64(digest: bytes) -> str:
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _ficheros_modelo(contenido: dict[str, str], nombre: str, version: str) -> dict[str, str]:
    """Normaliza rutas a partir de «<nombre>/» y filtra la versión indicada."""
    prefijo = f"{nombre}/{nombre}-{version}/"
    salida = {}
    for ruta, valor in contenido.items():
        indice = ruta.find(prefijo)
        if indice >= 0:
            salida[ruta[indice:]] = valor
    return salida


def _contenido_conda(paquete: bytes, nombre_fichero: str) -> dict[str, str]:
    resultado: dict[str, str] = {}

    def _desde_tar(datos_tar) -> None:
        with tarfile.open(fileobj=datos_tar, mode="r:*") as tf:
            for miembro in tf.getmembers():
                if miembro.isfile():
                    resultado[miembro.name] = _b64(hashlib.sha256(tf.extractfile(miembro).read()).digest())

    if nombre_fichero.endswith(".tar.bz2"):
        _desde_tar(io.BytesIO(paquete))
        return resultado
    # .conda: zip con pkg-*.tar.zst
    with zipfile.ZipFile(io.BytesIO(paquete)) as zf:
        interno = next(n for n in zf.namelist() if n.startswith("pkg-") and n.endswith(".tar.zst"))
        comprimido = zf.read(interno)
    zstd = shutil.which("zstd")
    if not zstd:
        raise RuntimeError("falta el programa zstd para abrir paquetes .conda")
    with tempfile.TemporaryDirectory() as tmp:
        origen = Path(tmp) / "pkg.tar.zst"
        origen.write_bytes(comprimido)
        subprocess.run([zstd, "-q", "-d", str(origen), "-o", str(Path(tmp) / "pkg.tar")], check=True)  # noqa: S603
        with open(Path(tmp) / "pkg.tar", "rb") as handle:
            _desde_tar(handle)
    return resultado


def _comparar(etiqueta: str, referencia: dict[str, str], otro: dict[str, str],
              confirmaciones: list[str], fallos: list[str]) -> None:
    if not otro:
        print(f"      {etiqueta}: no contiene esta versión del modelo")
        return
    distintos = sorted(r for r in referencia if r in otro and otro[r] != referencia[r])
    ausentes = sorted(r for r in referencia if r not in otro)
    iguales = len(referencia) - len(distintos) - len(ausentes)
    print(f"      {etiqueta}: {iguales} iguales, {len(distintos)} distintos, {len(ausentes)} ausentes")
    for ruta in (distintos + ausentes)[:10]:
        print(f"        - {ruta}")
    if distintos:
        fallos.append(f"{etiqueta}: el contenido del modelo difiere")
    elif not ausentes:
        confirmaciones.append(f"{etiqueta} ({iguales} ficheros idénticos)")


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

    version = tag.rsplit("-", 1)[-1]
    referencia = _ficheros_modelo(_contenido_modelo(wheel_github), nombre, version)
    print(f"    Ficheros del modelo en el wheel de GitHub: {len(referencia)}")
    if not referencia:
        fallos.append("el wheel de GitHub no contiene la carpeta del modelo esperada")

    print("[3] Paquetes conda construidos por terceros:")
    for canal in ("conda-forge", "main"):
        etiqueta = f"Anaconda {canal}"
        try:
            ficheros = json.loads(_get(
                f"https://api.anaconda.org/package/{canal}/spacy-model-{nombre}/files"
            ))
            candidatos = [f for f in ficheros if f.get("version") == version]
            if not candidatos:
                print(f"      {etiqueta}: sin versión {version}")
                continue
            elegido = sorted(candidatos, key=lambda f: not str(f.get("basename", "")).endswith(".tar.bz2"))[0]
            url_pkg = elegido.get("download_url", "")
            if url_pkg.startswith("//"):
                url_pkg = "https:" + url_pkg
            paquete = _get(url_pkg)
            sha_pkg = hashlib.sha256(paquete).hexdigest()
            if elegido.get("sha256") and elegido["sha256"] != sha_pkg:
                fallos.append(f"{etiqueta}: el paquete descargado no coincide con su sha256 publicado")
                continue
            print(f"      {etiqueta}: {elegido.get('basename')} (subido {elegido.get('upload_time')})")
            otro = _ficheros_modelo(_contenido_conda(paquete, str(elegido.get("basename"))), nombre, version)
            _comparar(etiqueta, referencia, otro, confirmaciones, fallos)
        except Exception as exc:  # noqa: BLE001
            print(f"      {etiqueta}: no disponible ({type(exc).__name__}: {exc})")

    print("[4] Hugging Face:")
    try:
        arbol = json.loads(_get(f"https://huggingface.co/api/models/spacy/{nombre}/tree/main"))
        ruedas = [e["path"] for e in arbol if str(e.get("path", "")).endswith(".whl")]
        if not ruedas:
            raise LookupError("sin wheels en el repositorio")
        wheel_hf = _get(f"https://huggingface.co/spacy/{nombre}/resolve/main/{ruedas[0]}")
        otro = _ficheros_modelo(_contenido_modelo(wheel_hf), nombre, version)
        _comparar(f"Hugging Face {ruedas[0]}", referencia, otro, confirmaciones, fallos)
    except Exception as exc:  # noqa: BLE001
        print(f"      no disponible ({type(exc).__name__}: {exc})")

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
