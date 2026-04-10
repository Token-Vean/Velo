#!/usr/bin/env python3
"""
Velo - Detector de datos sensibles para archiveros.
Ejecuta este fichero para iniciar la aplicación.
"""

import logging
import os
import socket
import sys
import threading
import time
import webbrowser

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)


def find_free_port(start=7780, end=7800):
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def open_browser(port):
    time.sleep(1.5)
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass


def main():
    try:
        from velo_engine.app import app
    except ImportError as exc:
        print(f"\n  [ERROR] Falta una dependencia: {exc}")
        print("  Ejecute: pip install -r requirements.txt\n")
        sys.exit(1)

    server_mode = "waitress"
    serve = None
    try:
        from waitress import serve as _serve
        serve = _serve
    except ImportError:
        server_mode = "flask"

    port = find_free_port()
    if port is None:
        print("\n  [ERROR] No se ha encontrado un puerto libre (7780-7800).\n")
        sys.exit(1)

    workspace = os.path.join(BASE_DIR, "workspace")
    os.makedirs(workspace, exist_ok=True)

    app.config["WORKSPACE"] = workspace
    app.config["PORT"] = port
    app.config["SERVER_PID"] = os.getpid()

    print("\n" + "=" * 55)
    print("  Velo - Detector de datos sensibles v0.2.5")
    print("=" * 55)
    print(f"\n  Interfaz:  http://localhost:{port}")
    print(f"  Workspace: {workspace}")
    print("  Modo:      LOCAL - Ningún dato sale de tu equipo\n")
    print("  [OK] Capa base: patrones regex")

    try:
        import spacy  # noqa: F401
        print("  [OK] spaCy instalado (solo se activará si hay modelo cargado)")
    except ImportError:
        print("  [--] spaCy no instalado (opcional)")

    try:
        import docx  # noqa: F401
        print("  [OK] Soporte DOCX")
    except ImportError:
        print("  [--] Sin soporte DOCX")

    try:
        import PyPDF2  # noqa: F401
        print("  [OK] Soporte PDF")
    except ImportError:
        print("  [--] Sin soporte PDF")

    try:
        import fitz  # noqa: F401
        print("  [OK] Revisión visual PDF (PyMuPDF)")
    except ImportError:
        print("  [--] Sin revisión visual PDF (opcional)")

    try:
        import PIL  # noqa: F401
        print("  [OK] Exportación visual por imagen (Pillow)")
    except ImportError:
        print("  [--] Sin exportación visual por imagen (opcional)")

    if server_mode == "waitress":
        print("  [OK] Servidor: waitress")
    else:
        print("  [--] waitress no está instalado; arrancando con servidor Flask")

    print("\n  Abriendo navegador...")
    print("  Para detener: use el botón 'Apagar' en la interfaz")
    print("                o cierre esta ventana\n")

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    logging.getLogger("waitress").setLevel(logging.ERROR)

    try:
        if serve is not None:
            serve(app, host="127.0.0.1", port=port, threads=4, _quiet=True)
        else:
            app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except Exception as exc:
        print(f"\n  [ERROR] El servidor se ha detenido: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
