#!/usr/bin/env python3
"""Escanea con GuardDog (Datadog) todos los paquetes de los locks.

GuardDog busca patrones típicos de paquetes maliciosos en el código fuente y
en los metadatos: descarga y ejecución de código, exfiltración, ofuscación,
código que se ejecuta al instalar o importar, suplantación de nombres, etc.
Produce falsos positivos en paquetes grandes y legítimos, así que el
resultado es un informe para revisar, no un veredicto.

Uso: escanear_guarddog.py [--salida DIR]   (requiere `guarddog` instalado)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _paquetes() -> list[tuple[str, str]]:
    paquetes = set()
    for linea in (RAIZ / "locks" / "restricciones.txt").read_text(encoding="utf-8").splitlines():
        coincidencia = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)", linea)
        if coincidencia:
            paquetes.add((coincidencia[1].lower(), coincidencia[2]))
    pip = re.search(r"^pip==(\S+)", (RAIZ / "locks" / "pip.lock").read_text(encoding="utf-8"), re.M)
    if pip:
        paquetes.add(("pip", pip[1].rstrip(" \\")))
    return sorted(paquetes)


def _escanear(paquete: tuple[str, str], salida: Path) -> tuple[str, str, dict | str]:
    nombre, version = paquete
    proceso = subprocess.run(  # noqa: S603
        ["guarddog", "pypi", "scan", nombre, "--version", version, "--output-format", "json"],
        capture_output=True, text=True, timeout=1800, check=False,
    )
    try:
        resultado = json.loads(proceso.stdout)
    except json.JSONDecodeError:
        return nombre, version, (proceso.stderr or proceso.stdout)[-800:]
    (salida / f"{nombre}-{version}.json").write_text(json.dumps(resultado, indent=2), encoding="utf-8")
    return nombre, version, resultado


def main() -> int:
    analizador = argparse.ArgumentParser()
    analizador.add_argument("--salida", type=Path, default=Path("guarddog"))
    opciones = analizador.parse_args()
    opciones.salida.mkdir(parents=True, exist_ok=True)

    paquetes = _paquetes()
    print(f"Paquetes a escanear: {len(paquetes)}")
    with ThreadPoolExecutor(max_workers=4) as grupo:
        resultados = list(grupo.map(lambda p: _escanear(p, opciones.salida), paquetes))

    reglas = Counter()
    errores = []
    print(f"\n{'paquete':28} {'versión':12} hallazgos  reglas")
    for nombre, version, resultado in resultados:
        if isinstance(resultado, str):
            errores.append(f"{nombre}=={version}: {resultado.strip()[:300]}")
            print(f"{nombre:28} {version:12} {'ERROR':>9}")
            continue
        detalle = {regla: datos for regla, datos in (resultado.get("results") or {}).items() if datos}
        reglas.update(detalle.keys())
        print(f"{nombre:28} {version:12} {resultado.get('issues', 0):9}  {', '.join(sorted(detalle)) or '-'}")

    print("\nDETALLE")
    for nombre, version, resultado in resultados:
        if isinstance(resultado, str):
            continue
        for regla, datos in sorted((resultado.get("results") or {}).items()):
            if not datos:
                continue
            print(f"\n## {nombre}=={version} · {regla}")
            elementos = datos if isinstance(datos, list) else [datos]
            for elemento in elementos[:8]:
                if isinstance(elemento, dict):
                    print(f"  - {elemento.get('location', '')}: {str(elemento.get('code', elemento.get('message', '')))[:240]}")
                else:
                    print(f"  - {str(elemento)[:300]}")
            if len(elementos) > 8:
                print(f"  ... y {len(elementos) - 8} más")

    print(f"\nReglas activadas (nº de paquetes): {dict(reglas.most_common())}")
    if errores:
        print("\nNo se pudieron escanear:")
        for error in errores:
            print(f"  - {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
