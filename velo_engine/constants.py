"""Constantes de aplicación para Velo."""

APP_NAME = "Velo"
APP_VERSION = "0.6.0"
# 3.11: Pillow 13 (correcciones de seguridad) ya no admite Python 3.10,
# que llego a fin de soporte en octubre de 2026.
MIN_PYTHON = (3, 11)

MAX_CONTENT_LENGTH_MB = 100
MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH_MB * 1024 * 1024
MAX_TEXT_LENGTH = 2_000_000
# Por encima de este número de hallazgos la revisión humana en la interfaz
# deja de ser viable (y el navegador se bloquea); se pide dividir el documento.
MAX_FINDINGS = 20_000
MAX_PDF_PAGES = 500
MAX_PDF_PAGES_VISUAL = 500
SESSION_TTL_HOURS = 24
# Los informes JSON exportados en workspace/ se purgan con el mismo TTL.
EXPORT_REPORT_TTL_HOURS = SESSION_TTL_HOURS
DOCX_MAX_ENTRIES = 5000
DOCX_MAX_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
DOCX_MAX_COMPRESSION_RATIO = 120
OCR_TIMEOUT_SECONDS = 25
# Subidas temporales (TXT/DOCX/PDF sin revisión visual) que sobrevivieron a
# una caída del proceso: se purgan pasado este tiempo.
ORPHAN_UPLOAD_TTL_SECONDS = 3600
