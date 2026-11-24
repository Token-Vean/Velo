#!/usr/bin/env python3
"""Audita el entorno virtual de Velo tras instalarlo desde los locks.

Se ejecuta con el Python del entorno (.venv). Falla si encuentra:
  - Ficheros .pth con código ejecutable (se ejecutan en CADA arranque de
    Python, un vector de ataque conocido), salvo el de setuptools, conocido.
  - sitecustomize.py o usercustomize.py (también se ejecutan al arrancar).
  - Paquetes instalados que no están en los locks, o en otra versión.
  - Ficheros de un paquete cuyo contenido no coincide con el RECORD del wheel
    (modificación posterior a la instalación).
  - Código suelto en site-packages que no pertenece a ningún paquete.
Informa además de los ejecutables y puntos de entrada que instala cada paquete.

Uso: .venv/bin/python tools/auditar_entorno.py [--locks DIR]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata as metadata
import re
import site
import sys
from pathlib import Path

PERMITIDOS_ENTORNO = {"pip", "setuptools", "wheel"}  # los pone ensurepip/venv
PTH_CONOCIDOS = {("setuptools", "distutils-precedence.pth")}
CODIGO = {".py", ".pth", ".so", ".pyd", ".dll", ".dylib", ".exe"}


def _normalizar(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def _versiones_lock(carpeta: Path) -> dict[str, set[str]]:
    versiones: dict[str, set[str]] = {}
    for lock in carpeta.glob("*.lock"):
        for linea in lock.read_text(encoding="utf-8").splitlines():
            exacta = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", linea)
            url = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*) @ \S+?-([0-9][^-/]*)-py", linea)
            coincidencia = exacta or url
            if coincidencia:
                versiones.setdefault(_normalizar(coincidencia[1]), set()).add(coincidencia[2])
    return versiones


def _hash_record(ruta: Path) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(ruta.read_bytes()).digest()).rstrip(b"=").decode()


def main() -> int:
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--locks", default=str(Path(__file__).resolve().parents[1] / "locks"))
    opciones = analizador.parse_args()

    if sys.prefix == sys.base_prefix:
        print("[ERROR] Ejecute este script con el Python del entorno virtual de Velo (.venv).")
        return 1

    fallos: list[str] = []
    # En Windows getsitepackages() incluye también la raíz del entorno
    # (con Scripts/python.exe): solo interesan las carpetas site-packages.
    sitios = [Path(p).resolve() for p in site.getsitepackages() if Path(p).name.lower() == "site-packages"]
    print(f"Entorno: {sys.prefix}\nsite-packages: {[str(s) for s in sitios]}")

    distribuciones = list(metadata.distributions(path=[str(s) for s in sitios]))
    propietario: dict[Path, str] = {}
    comprobados = 0
    for dist in distribuciones:
        nombre = _normalizar(dist.metadata["Name"])
        for fichero in dist.files or []:
            ruta = Path(dist.locate_file(fichero)).resolve()
            propietario[ruta] = nombre
            if fichero.hash and fichero.hash.mode == "sha256" and ruta.is_file():
                comprobados += 1
                if _hash_record(ruta) != fichero.hash.value:
                    fallos.append(f"{nombre}: {fichero} no coincide con su RECORD")
    print(f"Ficheros comprobados contra RECORD: {comprobados}")

    # Paquetes fuera de los locks
    esperadas = _versiones_lock(Path(opciones.locks))
    print(f"Paquetes instalados: {len(distribuciones)}")
    for dist in sorted(distribuciones, key=lambda d: _normalizar(d.metadata["Name"])):
        nombre, version = _normalizar(dist.metadata["Name"]), dist.version
        if nombre in PERMITIDOS_ENTORNO and nombre not in esperadas:
            print(f"  {nombre}=={version} (entorno virtual)")
            continue
        if nombre not in esperadas:
            fallos.append(f"paquete fuera de los locks: {nombre}=={version}")
        elif version not in esperadas[nombre]:
            fallos.append(f"{nombre}=={version} no es la versión del lock ({sorted(esperadas[nombre])})")

    # .pth y *customize
    for sitio in sitios:
        for pth in sorted(sitio.glob("*.pth")):
            lineas = [x.strip() for x in pth.read_text(encoding="utf-8", errors="replace").splitlines()]
            ejecutables = [x for x in lineas if x.startswith(("import ", "import\t"))]
            dueno = propietario.get(pth.resolve(), "(sin paquete)")
            print(f"  .pth: {pth.name} [{dueno}] líneas ejecutables: {len(ejecutables)}")
            for linea in ejecutables:
                print(f"        {linea[:160]}")
            if ejecutables and (dueno, pth.name) not in PTH_CONOCIDOS:
                fallos.append(f"{pth.name} ({dueno}) ejecuta código al arrancar Python")
        for nombre in ("sitecustomize.py", "usercustomize.py"):
            if (sitio / nombre).exists():
                fallos.append(f"{sitio / nombre} se ejecuta al arrancar Python")

        # Código suelto que no pertenece a ningún paquete
        for ruta in sitio.rglob("*"):
            if ruta.is_file() and ruta.suffix.lower() in CODIGO and "__pycache__" not in ruta.parts:
                if ruta.resolve() not in propietario:
                    fallos.append(f"código sin paquete propietario: {ruta}")

    # Ejecutables y puntos de entrada (informativo)
    print("Puntos de entrada instalados:")
    for dist in sorted(distribuciones, key=lambda d: _normalizar(d.metadata["Name"])):
        grupos: dict[str, list[str]] = {}
        for punto in dist.entry_points:
            grupos.setdefault(punto.group, []).append(punto.name)
        if grupos:
            resumen = "; ".join(f"{g}: {', '.join(sorted(n)[:6])}" for g, n in sorted(grupos.items()))
            print(f"  {_normalizar(dist.metadata['Name'])}: {resumen}")

    if fallos:
        print(f"[ERROR] {len(fallos)} incidencia(s):")
        for fallo in fallos:
            print(f"  - {fallo}")
        return 1
    print("[OK] Sin código de arranque oculto, sin paquetes fuera de los locks y sin ficheros alterados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
