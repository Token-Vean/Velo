"""Middleware y utilidades de seguridad para Velo.

- Protección CSRF real con token por sesión
- Verificación same-origin para peticiones mutantes
- Rate limiting en memoria
- Cabeceras de seguridad HTTP
- Autenticación básica opcional
- Log de auditoría con rotación
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from collections import defaultdict
from logging.handlers import RotatingFileHandler

from flask import g, jsonify, request, session

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30
MAX_PDF_PAGES = 500


def _default_workspace() -> str:
    """Devuelve una ruta de workspace segura por defecto."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_dir, "workspace")


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

    sec_fetch_site = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if sec_fetch_site in {"same-origin", "same-site", "none"}:
        return True

    return False


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
    if not log_dir:
        log_dir = _default_workspace()

    os.makedirs(log_dir, exist_ok=True)

    if _audit.handlers:
        return

    handler = RotatingFileHandler(
        os.path.join(log_dir, "velo_audit.log"),
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _audit.addHandler(handler)
    _audit.setLevel(logging.INFO)


def log_audit(action: str, detail: str = "") -> None:
    ip = request.remote_addr or "unknown"
    _audit.info("ACTION=%s | IP=%s | %s", action, ip, detail)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def init_security(app):
    """Registra todos los hooks de seguridad en la app Flask."""
    app.secret_key = app.config.get("SECRET_KEY") or secrets.token_hex(32)

    default_workspace = _default_workspace()
    app.config.setdefault("WORKSPACE", default_workspace)

    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Strict")
    app.config.setdefault("SESSION_COOKIE_SECURE", False)
    app.config.setdefault("SESSION_REFRESH_EACH_REQUEST", False)

    setup_audit_log(app.config.get("WORKSPACE", default_workspace))

    @app.before_request
    def _security_checks():
        ip = request.remote_addr or "unknown"

        g.csrf_token = _generate_csrf_token()

        if not _limiter.check(ip):
            logger.warning("Rate limit: %s", ip)
            return jsonify({"error": "Demasiadas peticiones."}), 429

        if request.path not in ("/api/status", "/static") and not request.path.startswith("/static"):
            if not _check_auth(app):
                return jsonify({"error": "Autenticación requerida."}), 401, {
                    "WWW-Authenticate": "Basic realm=Velo"
                }

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not _check_same_origin(app):
                logger.warning("CSRF same-origin rechazado: path=%s ip=%s", request.path, ip)
                return jsonify({"error": "Origen no permitido."}), 403

            if not _check_csrf():
                logger.warning("CSRF token inválido o ausente: path=%s ip=%s", request.path, ip)
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
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'"
        )

        if request.path == "/" or request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
