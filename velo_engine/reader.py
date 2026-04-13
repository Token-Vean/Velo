"""
Lector de ficheros.
Soporta TXT, DOCX y PDF (con texto extraible).
Las dependencias para DOCX y PDF son opcionales.

Estrategia de extraccion para PDF:
  1. PyMuPDF (fitz) - motor primario, alta calidad incluso con capas OCR.
  2. PyPDF2          - fallback si fitz no esta instalado.
"""

import logging
import os

logger = logging.getLogger("velo.reader")


def read_file(filepath):
    """Lee un fichero y devuelve su texto. Devuelve (texto, formato, error)."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".txt":
        return _read_txt(filepath)
    if ext == ".docx":
        return _read_docx(filepath)
    if ext == ".pdf":
        return _read_pdf(filepath)
    return None, ext, f"Formato no soportado: {ext}. Use TXT, DOCX o PDF."


def _read_txt(filepath):
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


def _read_docx(filepath):
    try:
        from docx import Document
    except ImportError:
        return None, "docx", "Para leer ficheros DOCX, instale python-docx: pip install python-docx"

    try:
        doc = Document(filepath)
        paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        text = "\n\n".join(paragraphs)
        if not text.strip():
            return None, "docx", "El documento DOCX no contiene texto extraible."
        return text, "docx", None
    except Exception as exc:
        return None, "docx", f"Error al leer DOCX: {exc}"


# ---------------------------------------------------------------------------
# PDF: motor primario (PyMuPDF) + fallback (PyPDF2)
# ---------------------------------------------------------------------------

def _read_pdf(filepath):
    """Intenta extraer texto con PyMuPDF; si no esta disponible, usa PyPDF2."""
    text, fmt, error = _read_pdf_fitz(filepath)
    if error and "instale" in (error or "").lower():
        logger.info("PyMuPDF no disponible, intentando PyPDF2 como fallback")
        return _read_pdf_pypdf2(filepath)
    return text, fmt, error


def _read_pdf_fitz(filepath):
    """Extraccion con PyMuPDF (fitz) - alta calidad."""
    try:
        import fitz  # noqa: F401
    except ImportError:
        return None, "pdf", (
            "Para leer ficheros PDF con maxima calidad, instale PyMuPDF: "
            "pip install PyMuPDF. Intentando motor alternativo..."
        )

    try:
        document = fitz.open(filepath)
        pages_text = []
        for page in document:
            page_text = (page.get_text("text") or "").strip()
            if page_text:
                pages_text.append(page_text)
        document.close()

        text = "\n\n".join(pages_text)
        if not text.strip():
            return None, "pdf", (
                "El PDF no contiene texto extraible (puede ser un documento escaneado). "
                "Para PDF escaneado haria falta un modulo OCR separado."
            )
        logger.info("PDF leido con PyMuPDF: %d paginas, %d caracteres", len(pages_text), len(text))
        return text, "pdf", None
    except Exception as exc:
        return None, "pdf", f"Error al leer PDF con PyMuPDF: {exc}"


def _read_pdf_pypdf2(filepath):
    """Extraccion con PyPDF2 - fallback de menor calidad."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None, "pdf", (
            "Para leer ficheros PDF, instale PyMuPDF (pip install PyMuPDF) "
            "o PyPDF2 (pip install PyPDF2)."
        )

    try:
        reader = PdfReader(filepath)
        pages_text = []
        for page in reader.pages:
            page_text = (page.extract_text() or "").strip()
            if page_text:
                pages_text.append(page_text)

        text = "\n\n".join(pages_text)
        if not text.strip():
            return None, "pdf", (
                "El PDF no contiene texto extraible (puede ser un documento escaneado). "
                "Para PDF escaneado haria falta un modulo OCR separado."
            )
        logger.warning(
            "PDF leido con PyPDF2 (fallback): %d paginas. "
            "Para mayor calidad en PDFs con OCR, instale PyMuPDF: pip install PyMuPDF",
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
            import PyPDF2  # noqa: F401
            pdf_available = True
            pdf_label = "PDF con texto (PyPDF2, calidad limitada)"
        except ImportError:
            pdf_label = "PDF (instale PyMuPDF o PyPDF2)"

    formats.append({"ext": ".pdf", "label": pdf_label, "available": pdf_available})
    return formats
