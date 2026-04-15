#!/usr/bin/env python3
"""Genera un paquete distribuible simplificado para usuarios no técnicos."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist_release" / "Velo"
APP_DIR = OUT / "app"

INCLUDE = [
    "run.py",
    "install.bat",
    "install.sh",
    "requirements.txt",
    "requirements-visual.txt",
    "requirements-nlp.txt",
    "velo_engine",
]

IGNORE = shutil.ignore_patterns(
    ".git",
    ".github",
    ".venv",
    "workspace",
    "dist",
    "dist_release",
    "build",
    "__pycache__",
    "*.pyc",
    "*.log",
)


def write_wrappers() -> None:
    (OUT / "INSTALAR_VELO.bat").write_text(
        '@echo off\ncd /d "%~dp0app"\ncall install.bat\n',
        encoding="utf-8",
    )
    (OUT / "INICIAR_VELO.bat").write_text(
        '@echo off\ncd /d "%~dp0app"\nif exist ".venv\\Scripts\\python.exe" (\n  .venv\\Scripts\\python.exe run.py\n) else (\n  echo Ejecute primero INSTALAR_VELO.bat\n  pause\n)\n',
        encoding="utf-8",
    )
    (OUT / "LEEME_PRIMERO.txt").write_text(
        "1. Ejecute INSTALAR_VELO.bat\n2. Después ejecute INICIAR_VELO.bat\n3. No mueva ni renombre la carpeta app\n",
        encoding="utf-8",
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    APP_DIR.mkdir(parents=True, exist_ok=True)

    for item in INCLUDE:
        src = ROOT / item
        dst = APP_DIR / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=IGNORE)
        else:
            shutil.copy2(src, dst)

    write_wrappers()
    print(f"Bundle generado en: {OUT}")


if __name__ == "__main__":
    main()
