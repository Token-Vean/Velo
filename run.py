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
from logging.handlers import RotatingFileHandler

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

APP_VERSION = "0.3.0"


def setup_logging(workspace: str) -> None:
    """Configura logging centralizado: fichero rotativo + consola."""
    log_dir = os.path.join(workspace, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, "velo.log")
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        "  %(levelname)-7s %(message)s",
    ))
    console_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Silenciar loggers ruidosos de terceros
    logging.getLogger("waitress").setLevel(logging.ERROR)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    logging.getLogger("velo").info("Logging inicializado: %s", log_path)


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


def _check_spacy() -> str:
    """Comprueba spaCy y modelo. Devuelve texto para consola."""
    try:
        import spacy
    except ImportError:
        return "  [--] spaCy no instalado (detección de nombres desactivada)\n" \
               "       Instale con: pip install -r requirements-nlp.txt"

    for model_name in ("es_core_news_md", "es_core_news_sm"):
        try:
            spacy.load(model_name)
            return f"  [OK] spaCy + modelo {model_name} (detección de nombres activa)"
        except OSError:
            continue

    return "  [!!] spaCy instalado pero SIN modelo español\n" \
           "       Instale con: python -m spacy download es_core_news_md"


def main():
    workspace = os.path.join(BASE_DIR, "workspace")
    os.makedirs(workspace, exist_ok=True)

    # Logging antes que nada
    setup_logging(workspace)
    logger = logging.getLogger("velo.startup")

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

    app.config["WORKSPACE"] = workspace
    app.config["PORT"] = port
    app.config["SERVER_PID"] = os.getpid()

    print("\n" + "=" * 55)
    print(f"  Velo - Detector de datos sensibles v{APP_VERSION}")
    print("=" * 55)
    print(f"\n  Interfaz:  http://localhost:{port}")
    print(f"  Workspace: {workspace}")
    print(f"  Logs:      {os.path.join(workspace, 'logs', 'velo.log')}")
    print("  Modo:      LOCAL - Ningún dato sale de tu equipo\n")
    print("  [OK] Capa base: patrones regex")

    # spaCy / NER
    print(_check_spacy())

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

    logger.info(
        "Velo v%s iniciado en http://localhost:%d (servidor=%s)",
        APP_VERSION, port, server_mode,
    )

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    try:
        if serve is not None:
            serve(app, host="127.0.0.1", port=port, threads=4, _quiet=True)
        else:
            app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except Exception as exc:
        logger.critical("El servidor se ha detenido inesperadamente: %s", exc, exc_info=True)
        print(f"\n  [ERROR] El servidor se ha detenido: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
