#!/usr/bin/env python3
"""Script de empaquetado para Velo."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from velo_engine.constants import APP_NAME

ENTRY_POINT = "run.py"


def build() -> None:
    print(f"Empaquetando {APP_NAME}...\n")

    try:
        import PyInstaller
        print(f"  ✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  ❌ PyInstaller no encontrado.")
        print("     Instálalo con: pip install pyinstaller")
        sys.exit(1)

    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    separator = ";" if sys.platform == "win32" else ":"
    template_path = os.path.join("velo_engine", "templates")
    static_path = os.path.join("velo_engine", "static")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onedir",
        "--noconsole" if sys.platform == "win32" else "--console",
        f"--add-data={template_path}{separator}velo_engine/templates",
        f"--add-data={static_path}{separator}velo_engine/static",
        "--hidden-import=velo_engine",
        "--hidden-import=velo_engine.app",
        "--hidden-import=velo_engine.constants",
        "--hidden-import=velo_engine.detector",
        "--hidden-import=velo_engine.reader",
        "--hidden-import=velo_engine.visual",
        "--clean",
        ENTRY_POINT,
    ]

    print(f"  Ejecutando: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)), check=False)

    if result.returncode == 0:
        dist_path = os.path.join("dist", APP_NAME)
        os.makedirs(os.path.join(dist_path, "workspace"), exist_ok=True)
        print(f"\n{'=' * 55}")
        print("  ✓ Empaquetado completado")
        print(f"  ▸ Ejecutable en: {dist_path}/")
        print(f"{'=' * 55}\n")
    else:
        print(f"\n  ❌ Error durante el empaquetado (código {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    build()
