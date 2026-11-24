"""Middleware y utilidades de seguridad para Velo.

- Protección CSRF real con token por sesión
- Validación de la cabecera Host (DNS rebinding)
- Verificación same-origin para peticiones mutantes
- Rate limiting en memoria
- Cabeceras de seguridad HTTP
- Autenticación básica opcional
- Log de auditoría con rotación
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections import defaultdict
from urllib.parse import urlparse
from logging.handlers import RotatingFileHandler

from flask import current_app, g, has_app_context, jsonify, request, session

logger = logging.getLogger(__name__)

# Nombres con los que se accede a Velo. Una web maliciosa que use DNS
# rebinding para apuntar su dominio a 127.0.0.1 sigue enviando su propio
# dominio en Host, así que se rechaza aquí. Ampliable con app.config["ALLOWED_HOSTS"].
LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30
MAX_PDF_PAGES = 500


def _default_workspace() -> str:
    """Devuelve una ruta de workspace segura por defecto."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_dir, "workspace")


_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def para_log(valor, maximo: int = 200) -> str:
    """Neutraliza un valor externo antes de escribirlo en un log.

    Evita la falsificación de líneas del log (una ruta con «%0A» decodificado)
    y las secuencias de escape que alteran la consola; además acota la
    longitud. Los saltos de línea se escapan, no se eliminan, para que se vea
    que venían en la petición.
    """
    texto = _CONTROL.sub("?", str(valor)[:maximo])
    return texto.replace("\r", "\\r").replace("\n", "\\n")


class _RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, ip: str) -> bool:
        now = time.time()
        self._hits[ip] = [t for t in self._hits[ip] if t > now - RATE_LIMIT_WINDOW]
        if len(self._hits[ip]) >= RATE_LIMIT_MAX:
            return False
        self._hits[ip].append(now)
        return True


_limiter = _RateLimiter()
_audit = logging.getLogger("velo.audit")


def _generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def _check_csrf() -> bool:
    expected = session.get("_csrf_token", "")
    provided = (request.headers.get("X-CSRF-Token") or "").strip()

    if not expected or not provided:
        return False

    return secrets.compare_digest(provided, expected)


def _allowed_origins(app) -> list[str]:
    port = app.config.get("PORT", 7780)
    return [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    ]


def _origin_allowed(origin_or_referer: str, allowed: list[str]) -> bool:
    if not origin_or_referer:
        return False

    value = origin_or_referer.strip()
    for base in allowed:
        if value == base or value.startswith(base + "/"):
            return True
    return False


def _check_same_origin(app) -> bool:
    allowed = _allowed_origins(app)

    origin = (request.headers.get("Origin") or "").strip()
    if origin:
        return _origin_allowed(origin, allowed)

    referer = (request.headers.get("Referer") or "").strip()
    if referer:
        return _origin_allowed(referer, allowed)

    # "same-site" no basta: cualquier otro servicio en localhost (otro puerto)
    # es same-site respecto a Velo.
    sec_fetch_site = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if sec_fetch_site in {"same-origin", "none"}:
        return True

    return False


def _host_allowed(app) -> bool:
    """True si la cabecera Host apunta a un nombre local permitido."""
    host = (request.headers.get("Host") or "").strip()
    if not host:
        # Sin Host (HTTP/1.0, clientes locales): no es un vector de rebinding.
        return True
    if any(ch in host for ch in "/?#@ \\"):
        return False
    try:
        hostname = urlparse(f"//{host}").hostname
    except ValueError:
        return False
    allowed = LOCAL_HOSTNAMES | frozenset(h.lower() for h in app.config.get("ALLOWED_HOSTS", ()))
    return bool(hostname) and hostname.lower() in allowed


def _check_auth(app) -> bool:
    user = app.config.get("AUTH_USER", "")
    pwd = app.config.get("AUTH_PASSWORD", "")
    if not user or not pwd:
        return True

    auth = request.authorization
    if not auth:
        return False

    return (
        secrets.compare_digest(auth.username or "", user)
        and secrets.compare_digest(auth.password or "", pwd)
    )


def setup_audit_log(log_dir: str | None = None) -> None:
    """Configura (o redirige) el log de auditoría a ``log_dir``.

    Hasta la 0.5.x se creaba al importar la aplicación, antes de que run.py
    fijase el workspace, y acababa en ``<carpeta de instalación>/workspace``:
    a menudo el Escritorio o Descargas, carpetas que OneDrive/iCloud
    sincronizan por defecto. Ahora run.py lo dirige a ``<workspace>/logs``.
    """
    if not log_dir:
        log_dir = _default_workspace()

    os.makedirs(log_dir, exist_ok=True)
    target = os.path.abspath(os.path.join(log_dir, "velo_audit.log"))

    for existing in list(_audit.handlers):
        if os.path.abspath(getattr(existing, "baseFilename", "")) == target:
            return
        _audit.removeHandler(existing)
        existing.close()

    handler = RotatingFileHandler(
        target,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _audit.addHandler(handler)
    _audit.setLevel(logging.INFO)


def _ensure_audit_handler() -> None:
    if _audit.handlers:
        return
    workspace = None
    if has_app_context():
        workspace = current_app.config.get("WORKSPACE")
    setup_audit_log(os.path.join(workspace, "logs") if workspace else None)


def log_audit(action: str, detail: str = "") -> None:
    _ensure_audit_handler()
    ip = request.remote_addr or "unknown"
    _audit.info("ACTION=%s | IP=%s | %s", para_log(action), para_log(ip), para_log(detail, 500))


_AUDIT_KEY: bytes | None = None


def _audit_key() -> bytes:
    """Clave local para seudonimizar textos en el log de auditoría.

    Un SHA-256 sin clave de un texto corto (un DNI pegado, un teléfono) se
    invierte por fuerza bruta en segundos: el espacio de DNI es de 10^8. Con
    HMAC y una clave aleatoria por instalación, guardada junto al log, el
    hash sigue permitiendo correlacionar análisis del mismo texto en ese
    equipo pero deja de revelar el contenido a quien solo tenga el log.
    """
    global _AUDIT_KEY
    if _AUDIT_KEY is not None:
        return _AUDIT_KEY

    key_path = None
    if has_app_context() and current_app.config.get("WORKSPACE"):
        key_path = os.path.join(current_app.config["WORKSPACE"], "logs", ".audit_key")
    if key_path:
        try:
            with open(key_path, "rb") as handle:
                key = handle.read()
            if len(key) >= 32:
                _AUDIT_KEY = key
                return key
        except OSError:
            pass
        try:
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            key = secrets.token_bytes(32)
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(key)
            _AUDIT_KEY = key
            return key
        except OSError as exc:
            logger.warning("No se pudo guardar la clave de auditoría; se usa una por proceso: %s", type(exc).__name__)

    _AUDIT_KEY = secrets.token_bytes(32)
    return _AUDIT_KEY


def hash_text(text: str) -> str:
    return hmac.new(_audit_key(), text.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def init_security(app):
    """Registra todos los hooks de seguridad en la app Flask."""
    app.secret_key = app.config.get("SECRET_KEY") or secrets.token_hex(32)

    default_workspace = _default_workspace()
    app.config.setdefault("WORKSPACE", default_workspace)

    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Strict")
    app.config.setdefault("SESSION_COOKIE_SECURE", False)
    app.config.setdefault("SESSION_REFRESH_EACH_REQUEST", False)

    # El log de auditoría se abre al primer uso (o desde run.py), no al
    # importar: así no se crea en la carpeta de instalación.

    @app.before_request
    def _security_checks():
        ip = request.remote_addr or "unknown"

        if not _host_allowed(app):
            logger.warning(
                "Host no permitido: %s path=%s ip=%s",
                para_log(request.headers.get("Host")), para_log(request.path), para_log(ip),
            )
            return jsonify({"error": "Host no permitido. Acceda mediante http://127.0.0.1 o http://localhost."}), 421

        g.csrf_token = _generate_csrf_token()

        # Los GET de assets de sesión (una imagen PNG por página) quedan
        # exentos del rate limiter: un PDF de 40 páginas legítimo superaría
        # el límite global solo con cargar la revisión visual. Siguen
        # protegidos por autenticación y por el saneado de rutas en app.py.
        is_session_asset = (
            request.method == "GET"
            and request.path.startswith("/api/session/")
            and "/asset/" in request.path
        )

        if not is_session_asset and not _limiter.check(ip):
            logger.warning("Rate limit: %s", para_log(ip))
            return jsonify({"error": "Demasiadas peticiones."}), 429

        if request.path not in ("/api/status", "/static") and not request.path.startswith("/static"):
            if not _check_auth(app):
                return jsonify({"error": "Autenticación requerida."}), 401, {
                    "WWW-Authenticate": "Basic realm=Velo"
                }

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not _check_same_origin(app):
                logger.warning("CSRF same-origin rechazado: path=%s ip=%s", para_log(request.path), para_log(ip))
                return jsonify({"error": "Origen no permitido."}), 403

            if not _check_csrf():
                logger.warning("CSRF token inválido o ausente: path=%s ip=%s", para_log(request.path), para_log(ip))
                return jsonify({"error": "Token CSRF inválido o ausente."}), 403

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), browsing-topics=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'"
        )

        if request.path == "/" or request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
