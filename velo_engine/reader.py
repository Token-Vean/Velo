"""Lector de ficheros con controles básicos de robustez."""

from __future__ import annotations

import logging
import os
import zipfile

from velo_engine.constants import (
    DOCX_MAX_COMPRESSION_RATIO,
    DOCX_MAX_ENTRIES,
    DOCX_MAX_UNCOMPRESSED_BYTES,
    MAX_PDF_PAGES,
)

logger = logging.getLogger("velo.reader")


def read_file(filepath: str):
    """Lee un fichero y devuelve (texto, formato, error)."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".txt":
        return _read_txt(filepath)
    if ext == ".docx":
        return _read_docx(filepath)
    if ext == ".pdf":
        return _read_pdf(filepath)
    return None, ext, f"Formato no soportado: {ext}. Use TXT, DOCX o PDF."


def _read_txt(filepath: str):
    try:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(filepath, "r", encoding=encoding) as file_obj:
                    text = file_obj.read()
                return text, "txt", None
            except UnicodeDecodeError:
                continue
        return None, "txt", "No se pudo decodificar el fichero de texto."
    except Exception as exc:
        return None, "txt", f"Error al leer TXT: {exc}"


def _preflight_docx(filepath: str) -> tuple[bool, str | None]:
    try:
        with zipfile.ZipFile(filepath) as zf:
            infos = zf.infolist()
            if len(infos) > DOCX_MAX_ENTRIES:
                return False, f"DOCX rechazado: demasiadas entradas ZIP ({len(infos)})."

            total_uncompressed = 0
            total_compressed = 0
            has_document_xml = False

            for info in infos:
                total_uncompressed += int(info.file_size or 0)
                total_compressed += int(info.compress_size or 0)
                if info.filename == "word/document.xml":
                    has_document_xml = True

            if not has_document_xml:
                return False, "DOCX inválido: falta word/document.xml."
            if total_uncompressed > DOCX_MAX_UNCOMPRESSED_BYTES:
                return False, "DOCX rechazado: tamaño descomprimido excesivo."

            compressed_floor = max(total_compressed, 1)
            ratio = total_uncompressed / compressed_floor
            if ratio > DOCX_MAX_COMPRESSION_RATIO:
                return False, "DOCX rechazado: ratio de compresión sospechoso."
    except zipfile.BadZipFile:
        return False, "El archivo DOCX no es un ZIP válido."
    except Exception as exc:
        return False, f"No se pudo inspeccionar el DOCX: {exc}"

    return True, None


def _read_docx(filepath: str):
    ok, error = _preflight_docx(filepath)
    if not ok:
        logger.warning("DOCX rechazado en preflight: %s", error)
        return None, "docx", error

    try:
        from docx import Document
    except ImportError:
        return None, "docx", "Para leer ficheros DOCX, instale python-docx: pip install python-docx"

    try:
        doc = Document(filepath)
        paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        text = "\n\n".join(paragraphs)
        if not text.strip():
            return None, "docx", "El documento DOCX no contiene texto extraíble."
        return text, "docx", None
    except Exception as exc:
        return None, "docx", f"Error al leer DOCX: {exc}"


def _read_pdf(filepath: str):
    text, fmt, error = _read_pdf_fitz(filepath)
    if error and "motor alternativo" in (error or "").lower():
        logger.info("PyMuPDF no disponible, intentando pypdf como fallback")
        return _read_pdf_pypdf(filepath)
    return text, fmt, error


def _read_pdf_fitz(filepath: str):
    try:
        import fitz
    except ImportError:
        return None, "pdf", (
            "Para leer ficheros PDF con máxima calidad, instale PyMuPDF: "
            "pip install PyMuPDF. Intentando motor alternativo..."
        )

    try:
        document = fitz.open(filepath)
        if document.page_count > MAX_PDF_PAGES:
            document.close()
            return None, "pdf", f"PDF rechazado: supera el máximo de {MAX_PDF_PAGES} páginas."

        pages_text = []
        for page in document:
            page_text = (page.get_text("text") or "").strip()
            if page_text:
                pages_text.append(page_text)
        document.close()

        text = "\n\n".join(pages_text)
        if not text.strip():
            return None, "pdf", (
                "El PDF no contiene texto extraíble (puede ser un documento escaneado). "
                "Para PDF escaneado hace falta OCR local."
            )
        logger.info("PDF leído con PyMuPDF: %d páginas, %d caracteres", len(pages_text), len(text))
        return text, "pdf", None
    except Exception as exc:
        return None, "pdf", f"Error al leer PDF con PyMuPDF: {exc}"


def _read_pdf_pypdf(filepath: str):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "pdf", (
            "Para leer ficheros PDF, instale PyMuPDF (pip install PyMuPDF) "
            "o pypdf (pip install pypdf)."
        )

    try:
        reader = PdfReader(filepath)
        if getattr(reader, "is_encrypted", False):
            return None, "pdf", "El PDF está cifrado y no puede analizarse sin descifrado previo."
        if len(reader.pages) > MAX_PDF_PAGES:
            return None, "pdf", f"PDF rechazado: supera el máximo de {MAX_PDF_PAGES} páginas."

        pages_text = []
        for page in reader.pages:
            page_text = (page.extract_text() or "").strip()
            if page_text:
                pages_text.append(page_text)

        text = "\n\n".join(pages_text)
        if not text.strip():
            return None, "pdf", (
                "El PDF no contiene texto extraíble (puede ser un documento escaneado). "
                "Para PDF escaneado hace falta OCR local."
            )
        logger.warning(
            "PDF leído con pypdf (fallback): %d páginas. Para mayor calidad en PDFs con OCR, instale PyMuPDF.",
            len(pages_text),
        )
        return text, "pdf", None
    except Exception as exc:
        return None, "pdf", f"Error al leer PDF: {exc}"


def supported_extensions():
    formats = [{"ext": ".txt", "label": "Texto plano", "available": True}]

    try:
        import docx  # noqa: F401
        formats.append({"ext": ".docx", "label": "Word DOCX", "available": True})
    except ImportError:
        formats.append({"ext": ".docx", "label": "Word DOCX (instale python-docx)", "available": False})

    pdf_available = False
    pdf_label = "PDF"
    try:
        import fitz  # noqa: F401
        pdf_available = True
        pdf_label = "PDF con texto (PyMuPDF)"
    except ImportError:
        try:
            import pypdf  # noqa: F401
            pdf_available = True
            pdf_label = "PDF con texto (pypdf, calidad limitada)"
        except ImportError:
            pdf_label = "PDF (instale PyMuPDF o pypdf)"

    formats.append({"ext": ".pdf", "label": pdf_label, "available": pdf_available})
    return formats
