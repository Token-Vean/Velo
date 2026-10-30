"""Constantes de aplicación para Velo."""

APP_NAME = "Velo"
APP_VERSION = "0.5.0"
# 3.11: Pillow 13 (correcciones de seguridad) ya no admite Python 3.10,
# que llego a fin de soporte en octubre de 2026.
MIN_PYTHON = (3, 11)

MAX_CONTENT_LENGTH_MB = 100
MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH_MB * 1024 * 1024
MAX_TEXT_LENGTH = 2_000_000
MAX_PDF_PAGES = 500
MAX_PDF_PAGES_VISUAL = 500
SESSION_TTL_HOURS = 24
# Los informes JSON exportados en workspace/ se purgan con el mismo TTL.
EXPORT_REPORT_TTL_HOURS = SESSION_TTL_HOURS
DOCX_MAX_ENTRIES = 5000
DOCX_MAX_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
DOCX_MAX_COMPRESSION_RATIO = 120
OCR_TIMEOUT_SECONDS = 25
