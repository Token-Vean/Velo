#!/usr/bin/env python3
"""
Velo - Detector de datos sensibles para archiveros.
Ejecuta este fichero para iniciar la aplicación.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler

from velo_engine.constants import APP_NAME, APP_VERSION, MIN_PYTHON, SESSION_TTL_HOURS

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)


def ensure_min_python() -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        current = ".".join(str(part) for part in sys.version_info[:3])
        print(f"\n  [ERROR] {APP_NAME} requiere Python {required}+ (actual: {current}).\n")
        sys.exit(1)


def setup_logging(workspace: str) -> None:
    """Configura logging centralizado: fichero rotativo + consola."""
    log_dir = os.path.join(workspace, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, "velo.log")
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("  %(levelname)-7s %(message)s"))
    console_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)

    logging.getLogger("waitress").setLevel(logging.ERROR)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("velo").info("Logging inicializado: %s", log_path)


def find_free_port(start: int = 7780, end: int = 7801) -> int | None:
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def open_browser_when_ready(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                webbrowser.open(f"http://localhost:{port}")
                return
        except Exception:
            time.sleep(0.25)
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass


def _probe_spacy_safe() -> str:
    logger = logging.getLogger("velo.startup")
    try:
        import spacy  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("spaCy no disponible o no cargable: %s", exc, exc_info=True)
        return (
            "  [--] spaCy no disponible o no cargable\n"
            "       Velo arrancará en modo regex.\n"
            f"       Detalle: {type(exc).__name__}: {exc}"
        )

    for model_name in ("es_core_news_md", "es_core_news_sm"):
        try:
            spacy.load(model_name)
            logger.info("spaCy operativo con modelo %s", model_name)
            return f"  [OK] spaCy + modelo {model_name} (detección de nombres activa)"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "spaCy cargó, pero el modelo %s no pudo abrirse: %s",
                model_name,
                exc,
                exc_info=True,
            )

    return (
        "  [--] spaCy instalado pero sin modelo cargable\n"
        "       Velo arrancará en modo regex hasta que se repare el modelo."
    )


def _log_optional_components() -> None:
    logger = logging.getLogger("velo.startup")
    try:
        status = _probe_spacy_safe()
        for line in status.splitlines():
            logger.info(line)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo no fatal al comprobar spaCy: %s", exc, exc_info=True)


def prune_stale_sessions(workspace: str, ttl_hours: int = SESSION_TTL_HOURS) -> int:
    sessions_root = os.path.join(workspace, "sessions")
    os.makedirs(sessions_root, exist_ok=True)

    cutoff = time.time() - ttl_hours * 3600
    removed = 0

    for name in os.listdir(sessions_root):
        path = os.path.join(sessions_root, name)
        if not os.path.isdir(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


def main() -> None:
    ensure_min_python()

    workspace = os.path.join(BASE_DIR, "workspace")
    os.makedirs(workspace, exist_ok=True)

    setup_logging(workspace)
    logger = logging.getLogger("velo.startup")

    try:
        from velo_engine.app import app
    except ImportError as exc:
        print(f"\n  [ERROR] Falta una dependencia: {exc}")
        print("  Ejecute el instalador o active el entorno virtual y use:")
        print("  python -m pip install -r requirements.txt\n")
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

    removed = prune_stale_sessions(workspace)

    print("\n" + "=" * 55)
    print(f"  {APP_NAME} - Detector de datos sensibles v{APP_VERSION}")
    print("=" * 55)
    print(f"\n  Interfaz:  http://localhost:{port}")
    print(f"  Workspace: {workspace}")
    print(f"  Logs:      {os.path.join(workspace, 'logs', 'velo.log')}")
    print("  Modo:      LOCAL - Ningún dato sale de tu equipo\n")

    if removed:
        print(f"  [OK] Sesiones visuales antiguas eliminadas: {removed}")

    print("  [OK] Capa base: patrones regex")
    print("  [..] Comprobando spaCy de forma segura (si falla, Velo seguirá arrancando)")

    try:
        import docx  # noqa: F401
        print("  [OK] Soporte DOCX")
    except Exception:
        print("  [--] Sin soporte DOCX")

    try:
        import pypdf  # noqa: F401
        print("  [OK] Soporte PDF")
    except Exception:
        print("  [--] Sin soporte PDF")

    try:
        import fitz  # noqa: F401
        print("  [OK] Revisión visual PDF (PyMuPDF)")
    except Exception:
        print("  [--] Sin revisión visual PDF (opcional)")

    try:
        import PIL  # noqa: F401
        print("  [OK] Exportación visual por imagen (Pillow)")
    except Exception:
        print("  [--] Sin exportación visual por imagen (opcional)")

    if server_mode == "waitress":
        print("  [OK] Servidor: waitress")
    else:
        print("  [--] waitress no está instalado; arrancando con servidor Flask")

    print("\n  Abriendo navegador cuando el servicio esté listo...")
    print("  Para detener: use el botón 'Apagar' en la interfaz")
    print("                o cierre esta ventana\n")

    logger.info(
        "%s v%s iniciado en http://localhost:%d (servidor=%s)",
        APP_NAME,
        APP_VERSION,
        port,
        server_mode,
    )

    threading.Thread(target=_log_optional_components, daemon=True).start()
    threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()

    try:
        if serve is not None:
            serve(app, host="127.0.0.1", port=port, threads=4, _quiet=True)
        else:
            app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except Exception as exc:  # noqa: BLE001
        logger.critical("El servidor se ha detenido inesperadamente: %s", exc, exc_info=True)
        print(f"\n  [ERROR] El servidor se ha detenido: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
