"""Validación defensiva de ficheros para Velo.

Este módulo centraliza controles previos al parsing de documentos. Su objetivo
no es garantizar que un fichero sea seguro en sentido absoluto, sino reducir
riesgos frecuentes antes de entregar el documento a librerías complejas como
PyMuPDF, pypdf, python-docx, Pillow o Tesseract.

Controles:
- Lista blanca de extensiones.
- Límite de tamaño.
- Comprobación básica de firma/magic bytes.
- Preflight ZIP/DOCX con límites de entradas, tamaño descomprimido y ratio.
- Preflight PDF mínimo.
- Detección de rutas de workspace potencialmente sincronizadas en la nube.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from velo_engine.constants import (
    DOCX_MAX_COMPRESSION_RATIO,
    DOCX_MAX_ENTRIES,
    DOCX_MAX_UNCOMPRESSED_BYTES,
    MAX_CONTENT_LENGTH,
)

ALLOWED_EXTENSIONS = {".txt", ".docx", ".pdf"}

SYNC_FOLDER_HINTS = (
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "icloud",
    "mega",
    "nextcloud",
    "syncthing",
)


@dataclass(frozen=True)
class FileValidationResult:
    """Resultado normalizado de validación de fichero."""

    filename: str
    extension: str
    size_bytes: int
    detected_type: str
    warnings: tuple[str, ...] = ()


class FileValidationError(ValueError):
    """Error de validación con mensaje seguro para interfaz."""

    def __init__(self, safe_message: str):
        super().__init__(safe_message)
        self.safe_message = safe_message


def _extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def _file_size(path: str | os.PathLike[str]) -> int:
    try:
        return int(os.path.getsize(path))
    except OSError as exc:
        raise FileValidationError("No se pudo comprobar el tamaño del fichero.") from exc


def _read_prefix(path: str | os.PathLike[str], length: int = 16) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read(length)
    except OSError as exc:
        raise FileValidationError("No se pudo inspeccionar el contenido del fichero.") from exc


def workspace_sync_warnings(path: str | os.PathLike[str]) -> tuple[str, ...]:
    """Devuelve advertencias si la ruta parece estar bajo una carpeta sincronizada."""

    normalized = str(Path(path).expanduser().resolve()).lower()
    warnings: list[str] = []
    if any(hint in normalized for hint in SYNC_FOLDER_HINTS):
        warnings.append(
            "El workspace parece estar dentro de una carpeta sincronizada. "
            "Para documentos sensibles se recomienda usar una carpeta local no sincronizada."
        )
    return tuple(warnings)


def _validate_txt(path: str | os.PathLike[str]) -> str:
    prefix = _read_prefix(path, 8)
    if prefix.startswith(b"\x00\x00") or prefix.startswith(b"MZ"):
        raise FileValidationError("El fichero TXT no parece texto plano válido.")
    return "txt"


def _validate_pdf(path: str | os.PathLike[str]) -> str:
    prefix = _read_prefix(path, 8)
    if not prefix.startswith(b"%PDF-"):
        raise FileValidationError("El fichero tiene extensión PDF, pero no presenta firma PDF válida.")

    # Comprobación final ligera: muchos PDFs finalizan con %%EOF, pero no todos
    # están perfectamente normalizados. Por eso solo se rechazan ficheros
    # claramente vacíos o con cabecera inválida; el parser hará el resto.
    return "pdf"


def _validate_docx(path: str | os.PathLike[str]) -> str:
    prefix = _read_prefix(path, 4)
    if not prefix.startswith(b"PK"):
        raise FileValidationError("El fichero tiene extensión DOCX, pero no presenta estructura ZIP válida.")

    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > DOCX_MAX_ENTRIES:
                raise FileValidationError(
                    f"DOCX rechazado: demasiadas entradas internas ({len(infos)})."
                )

            total_uncompressed = 0
            total_compressed = 0
            has_document_xml = False

            for info in infos:
                filename = info.filename.replace("\\", "/")
                if filename.startswith("/") or ".." in Path(filename).parts:
                    raise FileValidationError("DOCX rechazado: contiene rutas internas sospechosas.")

                total_uncompressed += int(info.file_size or 0)
                total_compressed += int(info.compress_size or 0)

                if filename == "word/document.xml":
                    has_document_xml = True

            if not has_document_xml:
                raise FileValidationError("DOCX inválido: falta word/document.xml.")

            if total_uncompressed > DOCX_MAX_UNCOMPRESSED_BYTES:
                raise FileValidationError("DOCX rechazado: tamaño descomprimido excesivo.")

            ratio = total_uncompressed / max(total_compressed, 1)
            if ratio > DOCX_MAX_COMPRESSION_RATIO:
                raise FileValidationError("DOCX rechazado: ratio de compresión sospechoso.")

    except zipfile.BadZipFile as exc:
        raise FileValidationError("El archivo DOCX no es un ZIP válido.") from exc
    except FileValidationError:
        raise
    except Exception as exc:
        raise FileValidationError("No se pudo inspeccionar de forma segura el DOCX.") from exc

    return "docx"


def validate_uploaded_file(
    path: str | os.PathLike[str],
    original_filename: str,
    *,
    max_bytes: int | None = None,
) -> FileValidationResult:
    """Valida un fichero subido antes de entregarlo a los parsers.

    Args:
        path: ruta local del fichero ya guardado.
        original_filename: nombre original aportado por el usuario.
        max_bytes: límite de tamaño. Si no se indica, usa MAX_CONTENT_LENGTH.

    Returns:
        FileValidationResult.

    Raises:
        FileValidationError: cuando el fichero debe rechazarse.
    """

    ext = _extension(original_filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError("Formato no permitido. Use TXT, DOCX o PDF.")

    size_bytes = _file_size(path)
    effective_max = MAX_CONTENT_LENGTH if max_bytes is None else int(max_bytes)

    if size_bytes <= 0:
        raise FileValidationError("El fichero está vacío.")

    if size_bytes > effective_max:
        max_mb = effective_max / (1024 * 1024)
        raise FileValidationError(f"El fichero excede el tamaño máximo permitido ({max_mb:.0f} MB).")

    if ext == ".txt":
        detected = _validate_txt(path)
    elif ext == ".pdf":
        detected = _validate_pdf(path)
    elif ext == ".docx":
        detected = _validate_docx(path)
    else:
        raise FileValidationError("Formato no permitido. Use TXT, DOCX o PDF.")

    return FileValidationResult(
        filename=os.path.basename(original_filename or "document"),
        extension=ext,
        size_bytes=size_bytes,
        detected_type=detected,
        warnings=workspace_sync_warnings(Path(path).parent),
    )
