"""Middleware y utilidades de seguridad para Velo.

- Proteccion CSRF con token por sesion
- Rate limiting en memoria
- Cabeceras de seguridad HTTP
- Autenticacion basica opcional
- Log de auditoria con rotacion
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from flask import request, jsonify, session, g

logger = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30
MAX_PDF_PAGES = 100


# ── Rate limiter ─────────────────────────────────────────
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


# ── CSRF ─────────────────────────────────────────────────
def _generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def _check_csrf() -> bool:
    token = request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf_token", "")
    if not expected:
        return True  # Primera peticion, aun no hay token
    return secrets.compare_digest(token, expected)


# ── Auth basica ──────────────────────────────────────────
def _check_auth(app) -> bool:
    user = app.config.get("AUTH_USER", "")
    pwd = app.config.get("AUTH_PASSWORD", "")
    if not user or not pwd:
        return True
    auth = request.authorization
    if not auth:
        return False
    return (secrets.compare_digest(auth.username, user)
            and secrets.compare_digest(auth.password, pwd))


# ── Audit logging ────────────────────────────────────────
_audit = logging.getLogger("velo.audit")


def setup_audit_log(log_dir: str = "./workspace") -> None:
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "velo_audit.log"),
        maxBytes=5_000_000, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(message)s"
    ))
    _audit.addHandler(handler)
    _audit.setLevel(logging.INFO)


def log_audit(action: str, detail: str = "") -> None:
    ip = request.remote_addr or "unknown"
    _audit.info("ACTION=%s | IP=%s | %s", action, ip, detail)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Registro del middleware en la app ────────────────────
def init_security(app):
    """Registra todos los hooks de seguridad en la app Flask."""
    app.secret_key = app.config.get("SECRET_KEY") or secrets.token_hex(32)

    setup_audit_log(app.config.get("WORKSPACE", "./workspace"))

    @app.before_request
    def _security_checks():
        ip = request.remote_addr or "unknown"

        # Rate limiting
        if not _limiter.check(ip):
            logger.warning("Rate limit: %s", ip)
            return jsonify({"error": "Demasiadas peticiones."}), 429

        # Auth basica
        if request.path not in ("/api/status", "/static") and not request.path.startswith("/static"):
            if not _check_auth(app):
                return jsonify({"error": "Autenticacion requerida."}), 401, {
                    "WWW-Authenticate": "Basic realm=Velo"
                }

        # CSRF en POST (excepto si es API local de confianza)
        if request.method == "POST":
            # Comprobar origen
            origin = request.headers.get("Origin", "")
            referer = request.headers.get("Referer", "")
            port = app.config.get("PORT", 7780)
            allowed = [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]
            if origin and not any(origin.startswith(a) for a in allowed):
                logger.warning("CSRF: origen no permitido: %s", origin)
                return jsonify({"error": "Origen no permitido."}), 403

        # Inyectar CSRF token
        g.csrf_token = _generate_csrf_token()

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'"
        )
        return response
