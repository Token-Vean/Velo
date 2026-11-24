#!/usr/bin/env python3
"""Procedencia de los paquetes de los locks.

1. Cada hash de cada lock debe corresponder a un fichero publicado en PyPI
   para ese paquete y versión (API JSON de PyPI). Un hash que no esté
   publicado indica un lock manipulado o un paquete retirado.
2. Para cada fichero, consulta si PyPI tiene atestaciones de procedencia
   (PEP 740, «Trusted Publishing»): un certificado Sigstore que vincula el
   fichero al repositorio y al workflow de CI que lo construyó. Con
   --verificar DIR verifica criptográficamente las atestaciones de los
   ficheros descargados en DIR (requiere el paquete pypi-attestations).
3. Compara los repositorios publicadores con locks/procedencia.json, revisado
   a mano: falla si un paquete que publicaba con atestaciones deja de hacerlo
   o si cambia el repositorio que lo publica.

Uso: verificar_procedencia.py [--verificar DIR] [--escribir-esperada]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESPERADA = RAIZ / "locks" / "procedencia.json"
AGENTE = {"User-Agent": "velo-verificacion-procedencia"}


def _get_json(url: str, aceptar: str = "application/json", intentos: int = 5):
    """GET con reintentos: son ~1600 consultas y PyPI corta alguna de vez en cuando."""
    peticion = urllib.request.Request(url, headers={**AGENTE, "Accept": aceptar})
    for intento in range(intentos):
        try:
            with urllib.request.urlopen(peticion, timeout=60) as respuesta:  # noqa: S310 (URL fija https)
                return json.loads(respuesta.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code < 500 and exc.code != 429 or intento == intentos - 1:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if intento == intentos - 1:
                raise
        time.sleep(2 ** intento)
    return None


def _entradas_locks() -> dict[tuple[str, str], set[str]]:
    entradas: dict[tuple[str, str], set[str]] = {}
    for lock in sorted((RAIZ / "locks").glob("*.lock")):
        actual = None
        for linea in lock.read_text(encoding="utf-8").splitlines():
            cabecera = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", linea)
            if cabecera:
                actual = (cabecera[1].lower(), cabecera[2])
                entradas.setdefault(actual, set())
            elif re.match(r"^\S", linea):
                actual = None  # URL directa (modelo spaCy) u otra cosa: no es de PyPI
            if actual:
                entradas[actual].update(re.findall(r"--hash=sha256:([0-9a-f]{64})", linea))
    return entradas


def _revisar(paquete: tuple[str, str], hashes: set[str]) -> dict:
    nombre, version = paquete
    datos = _get_json(f"https://pypi.org/pypi/{nombre}/{version}/json")
    if datos is None:
        return {"paquete": nombre, "version": version, "error": "versión no encontrada en PyPI"}
    publicados = {u["digests"]["sha256"]: u for u in datos.get("urls", [])}
    ajenos = sorted(hashes - publicados.keys())
    ficheros = [publicados[h] for h in hashes if h in publicados]
    repositorios: set[str] = set()
    con, sin = 0, 0
    for fichero in ficheros:
        procedencia = _get_json(
            f"https://pypi.org/integrity/{nombre}/{version}/{fichero['filename']}/provenance",
            "application/vnd.pypi.integrity.v1+json",
        )
        if procedencia and procedencia.get("attestation_bundles"):
            con += 1
            for paquete_firmado in procedencia["attestation_bundles"]:
                publicador = paquete_firmado.get("publisher", {})
                repositorios.add(f"{publicador.get('kind')}:{publicador.get('repository')}")
        else:
            sin += 1
    return {
        "paquete": nombre, "version": version, "ficheros": len(ficheros),
        "hashes_no_publicados": ajenos, "con_atestacion": con, "sin_atestacion": sin,
        "repositorios": sorted(repositorios),
    }


def _verificar_descargas(carpeta: Path) -> list[str]:
    """Verificación criptográfica (Sigstore) de los ficheros descargados."""
    from pypi_attestations import Distribution, Provenance

    fallos = []
    for fichero in sorted(carpeta.iterdir()):
        if not fichero.is_file():
            continue
        distribucion = Distribution.from_file(fichero)
        coincidencia = re.match(r"^(.+?)-(\d[^-]*)[-.]", fichero.name)
        if not coincidencia:
            continue
        nombre = re.sub(r"[-_.]+", "-", coincidencia[1]).lower()
        crudo = _get_json(
            f"https://pypi.org/integrity/{nombre}/{coincidencia[2]}/{fichero.name}/provenance",
            "application/vnd.pypi.integrity.v1+json",
        )
        if not crudo:
            print(f"  [--] {fichero.name}: sin atestación")
            continue
        procedencia = Provenance.model_validate(crudo)
        try:
            for paquete_firmado in procedencia.attestation_bundles:
                for atestacion in paquete_firmado.attestations:
                    atestacion.verify(paquete_firmado.publisher, distribucion)
            repos = sorted({getattr(p.publisher, "repository", "?") for p in procedencia.attestation_bundles})
            print(f"  [OK] {fichero.name}: firma válida, publicado desde {', '.join(repos)}")
        except Exception as exc:  # noqa: BLE001
            fallos.append(f"{fichero.name}: atestación NO válida ({type(exc).__name__}: {exc})")
            print(f"  [X] {fallos[-1]}")
    return fallos


def main() -> int:
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--verificar", type=Path)
    analizador.add_argument("--escribir-esperada", action="store_true")
    opciones = analizador.parse_args()

    entradas = _entradas_locks()
    with ThreadPoolExecutor(max_workers=12) as grupo:
        resultados = list(grupo.map(lambda par: _revisar(*par), entradas.items()))

    fallos: list[str] = []
    print(f"{'paquete':28} {'versión':12} ficheros  con/sin atestación  publicador")
    for r in sorted(resultados, key=lambda x: x["paquete"]):
        if "error" in r:
            fallos.append(f"{r['paquete']}=={r['version']}: {r['error']}")
            continue
        print(f"{r['paquete']:28} {r['version']:12} {r['ficheros']:8}  {r['con_atestacion']:3}/{r['sin_atestacion']:<3}"
              f"              {', '.join(r['repositorios']) or '-'}")
        if r["hashes_no_publicados"]:
            fallos.append(f"{r['paquete']}=={r['version']}: hashes del lock que PyPI no publica: {r['hashes_no_publicados']}")

    total = sum(r.get("ficheros", 0) for r in resultados)
    firmados = sum(r.get("con_atestacion", 0) for r in resultados)
    paquetes_firmados = sum(1 for r in resultados if r.get("con_atestacion"))
    print(f"\nFicheros: {total}; con atestación: {firmados}. Paquetes con atestación: {paquetes_firmados}/{len(resultados)}")

    actual = {r["paquete"]: r["repositorios"] for r in resultados if r.get("repositorios")}
    if opciones.escribir_esperada:
        ESPERADA.write_text(json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Escrito {ESPERADA}")
    elif ESPERADA.exists():
        esperada = json.loads(ESPERADA.read_text(encoding="utf-8"))
        presentes = {r["paquete"] for r in resultados}
        for paquete, repos in esperada.items():
            if paquete not in presentes:
                continue
            if paquete not in actual:
                fallos.append(f"{paquete}: publicaba con atestación ({repos}) y esta versión no la tiene")
            elif actual[paquete] != repos:
                fallos.append(f"{paquete}: cambia el publicador {repos} -> {actual[paquete]}")
        for paquete in sorted(set(actual) - set(esperada)):
            print(f"[AVISO] {paquete} publica ahora con atestación desde {actual[paquete]}: revise y añádalo a procedencia.json")

    if opciones.verificar:
        print(f"\nVerificación criptográfica de los ficheros de {opciones.verificar}:")
        fallos.extend(_verificar_descargas(opciones.verificar))

    if fallos:
        print(f"[ERROR] {len(fallos)} incidencia(s):")
        for fallo in fallos:
            print(f"  - {fallo}")
        return 1
    print("[OK] Todos los hashes están publicados en PyPI y la procedencia coincide con la esperada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
