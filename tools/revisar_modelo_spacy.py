#!/usr/bin/env python3
"""Revisa el paquete instalado del modelo spaCy: código, configuración y pickle.

Un modelo de spaCy no es solo datos: trae un __init__.py y una configuración
que nombra funciones registradas que spaCy invoca al cargarlo. Este script,
ejecutado con el Python del entorno de Velo, comprueba que:
  - El único código Python es el __init__.py estándar de los modelos de
    Explosion (importa de pathlib y spacy.util y define load()), y lo imprime.
  - Todas las funciones a las que remite config.cfg (@architectures, @layers,
    @tokenizers, etc.) se resuelven en el registro de spaCy a código de
    spaCy, spacy-legacy o thinc, no a código ajeno.
  - Ningún fichero es un pickle de Python (deserializarlo puede ejecutar
    código) ni un array NumPy de objetos (que se guarda con pickle).
  - Nada en el paquete es ejecutable nativo.
"""

from __future__ import annotations

import ast
import importlib.util
import pickletools
import re
import sys
from pathlib import Path

MODELO = "es_core_news_md"
IMPORTS_PERMITIDOS = {"pathlib", "spacy.util"}
MODULOS_PERMITIDOS = ("spacy", "spacy_legacy", "thinc")
NATIVOS = {".so", ".pyd", ".dll", ".dylib", ".exe"}


def _es_pickle(datos: bytes) -> bool:
    if len(datos) < 2 or datos[0] != 0x80 or datos[1] not in range(2, 6):
        return False
    try:
        for _ in pickletools.genops(datos):
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    especificacion = importlib.util.find_spec(MODELO)
    if especificacion is None or not especificacion.submodule_search_locations:
        print(f"[ERROR] {MODELO} no está instalado en este entorno")
        return 1
    raiz = Path(list(especificacion.submodule_search_locations)[0])
    ficheros = sorted(p for p in raiz.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    print(f"Paquete: {raiz}\nFicheros: {len(ficheros)}")
    fallos: list[str] = []

    codigo = [p for p in ficheros if p.suffix == ".py"]
    for fichero in codigo:
        fuente = fichero.read_text(encoding="utf-8")
        print(f"--- {fichero.relative_to(raiz)} ---\n{fuente.rstrip()}\n---")
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                fallos.extend(f"{fichero.name} importa {a.name}" for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module not in IMPORTS_PERMITIDOS:
                fallos.append(f"{fichero.name} importa de {nodo.module}")
            elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id in (
                "exec", "eval", "compile", "__import__", "open",
            ):
                fallos.append(f"{fichero.name} llama a {nodo.func.id}()")
    if [p.name for p in codigo] != ["__init__.py"]:
        fallos.append(f"código Python inesperado: {[str(p.relative_to(raiz)) for p in codigo]}")

    from spacy.util import registry

    referencias: set[tuple[str, str]] = set()
    for config in raiz.rglob("config.cfg"):
        for linea in config.read_text(encoding="utf-8").splitlines():
            coincidencia = re.match(r'^\s*@(\w+)\s*=\s*"?([^"\s]+)"?', linea)
            if coincidencia:
                referencias.add((coincidencia[1], coincidencia[2]))
    print(f"Funciones registradas que usa config.cfg ({len(referencias)}):")
    for registro, nombre in sorted(referencias):
        try:
            funcion = registry.get(registro, nombre)
            modulo = getattr(funcion, "__module__", "") or ""
        except Exception as exc:  # noqa: BLE001
            fallos.append(f"config.cfg remite a {registro}:{nombre}, que no está registrada ({type(exc).__name__})")
            continue
        print(f"  @{registro} {nombre} -> {modulo}")
        if modulo.split(".")[0] not in MODULOS_PERMITIDOS:
            fallos.append(f"config.cfg remite a código ajeno a spaCy/thinc: {registro}:{nombre} ({modulo})")

    pickles = []
    for fichero in ficheros:
        if fichero.suffix.lower() in NATIVOS:
            fallos.append(f"binario nativo en el modelo: {fichero.relative_to(raiz)}")
        cabecera = fichero.read_bytes()[:256]
        if cabecera.startswith(b"\x93NUMPY") and re.search(rb"'descr':\s*'\|O'", cabecera):
            fallos.append(f"array NumPy de objetos (pickle): {fichero.relative_to(raiz)}")
        if _es_pickle(fichero.read_bytes()):
            pickles.append(str(fichero.relative_to(raiz)))
    if pickles:
        fallos.append(f"ficheros pickle: {pickles}")
    print(f"Ficheros pickle: {len(pickles)}")

    if fallos:
        print(f"[ERROR] {len(fallos)} incidencia(s):")
        for fallo in fallos:
            print(f"  - {fallo}")
        return 1
    print("[OK] El modelo solo contiene el __init__.py estándar, datos y configuración de spaCy; sin pickle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
