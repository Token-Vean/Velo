#!/usr/bin/env python3
"""
Script de empaquetado para Velo.
No forma parte del flujo principal de ejecución; es una utilidad de distribución local.
Genera un ejecutable independiente por sistema operativo.

Requisitos:
    pip install pyinstaller

Uso:
    python build.py

Resultado:
    dist/Velo/       (carpeta con el ejecutable y dependencias)
    dist/Velo.exe    (Windows) o dist/Velo (Mac/Linux)
"""

import subprocess
import sys
import os
import shutil

APP_NAME = "Velo"
ENTRY_POINT = "run.py"


def build():
    print(f"Empaquetando {APP_NAME}...\n")

    # Verificar PyInstaller
    try:
        import PyInstaller
        print(f"  ✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  ❌ PyInstaller no encontrado.")
        print("     Instálalo con: pip install pyinstaller")
        sys.exit(1)

    # Limpiar builds anteriores
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    # Rutas de datos adicionales (templates, static)
    separator = ";" if sys.platform == "win32" else ":"
    template_path = os.path.join("velo_engine", "templates")
    static_path = os.path.join("velo_engine", "static")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onedir",                              # Carpeta (más rápido que --onefile)
        "--noconsole" if sys.platform == "win32" else "--console",
        f"--add-data={template_path}{separator}velo_engine/templates",
        f"--add-data={static_path}{separator}velo_engine/static",
        "--hidden-import=velo_engine",
        "--hidden-import=velo_engine.app",
        "--hidden-import=velo_engine.detector",
        "--hidden-import=velo_engine.reader",
        "--hidden-import=velo_engine.visual",
        "--clean",
        ENTRY_POINT,
    ]

    print(f"  Ejecutando: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        dist_path = os.path.join("dist", APP_NAME)
        print(f"\n{'=' * 55}")
        print(f"  ✓ Empaquetado completado")
        print(f"  ▸ Ejecutable en: {dist_path}/")
        print(f"{'=' * 55}")
        print(f"\n  Para distribuir, comprime la carpeta '{dist_path}'")
        print(f"  y compártela. El usuario solo tiene que descomprimir")
        print(f"  y ejecutar '{APP_NAME}' (doble clic).\n")

        # Crear carpeta workspace en dist
        os.makedirs(os.path.join(dist_path, "workspace"), exist_ok=True)
    else:
        print(f"\n  ❌ Error durante el empaquetado (código {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    build()
