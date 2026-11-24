#!/usr/bin/env python3
"""Comprueba que los locks de locks/ corresponden a los requirements*.txt.

Falla si un requirements*.txt fija una versión (==) o una URL que no aparece
igual en su lock, si una dependencia declarada falta en el lock, o si alguna
entrada del lock no lleva hash. Pensado para CI: cuando Dependabot actualiza
un requirements*.txt, este control obliga a regenerar los locks (workflow
«dependencias-bloqueadas» con regenerar = true). Solo biblioteca estándar.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PARES = {
    "requirements.txt": "locks/requirements.lock",
    "requirements-visual.txt": "locks/requirements-visual.lock",
    "requirements-nlp.txt": "locks/requirements-nlp.lock",
}
NOMBRE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalizar(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def _entradas_lock(texto: str) -> dict[str, list[str]]:
    """{nombre normalizado: [especificación completa de cada entrada]}."""
    entradas: dict[str, list[str]] = {}
    bloque: list[str] = []

    def _cerrar() -> None:
        if not bloque:
            return
        cabecera = bloque[0].rstrip("\\").strip()
        coincidencia = NOMBRE.match(cabecera)
        if coincidencia:
            entradas.setdefault(_normalizar(coincidencia[1]), []).append(" ".join(bloque))

    for linea in texto.splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        if not linea.startswith(" "):
            _cerrar()
            bloque = [linea]
        else:
            bloque.append(linea.strip())
    _cerrar()
    return entradas


def main() -> int:
    errores: list[str] = []
    for entrada, lock in PARES.items():
        ruta_lock = RAIZ / lock
        if not ruta_lock.exists():
            errores.append(f"falta {lock}")
            continue
        entradas = _entradas_lock(ruta_lock.read_text(encoding="utf-8"))
        for nombre, especificaciones in entradas.items():
            for especificacion in especificaciones:
                if "--hash=sha256:" not in especificacion:
                    errores.append(f"{lock}: {nombre} no tiene hash")
        for linea in (RAIZ / entrada).read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            if not linea:
                continue
            coincidencia = NOMBRE.match(linea)
            if not coincidencia:
                continue
            nombre = _normalizar(coincidencia[1])
            if nombre not in entradas:
                errores.append(f"{lock}: falta {nombre} (declarado en {entrada})")
                continue
            if " @ " in linea:
                url = linea.split(" @ ", 1)[1].strip()
                if not any(url in e for e in entradas[nombre]):
                    errores.append(f"{lock}: {nombre} no apunta a {url}")
            else:
                exacta = re.search(r"==\s*([^\s,;]+)", linea)
                if exacta and not any(
                    re.search(rf"=={re.escape(exacta[1])}(\s|;|\\|$)", e) for e in entradas[nombre]
                ):
                    errores.append(f"{lock}: {nombre} no está en {exacta[1]} (como pide {entrada})")

    if errores:
        print("[ERROR] Los locks no corresponden a los requirements*.txt:")
        for error in errores:
            print(f"  - {error}")
        print(
            "Regenérelos: Actions > dependencias-bloqueadas > Run workflow sobre esta rama "
            "con «regenerar» marcado (o tools/generar_locks.sh con uv)."
        )
        return 1
    print("[OK] Locks coherentes con requirements*.txt y con hash en todas las entradas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
