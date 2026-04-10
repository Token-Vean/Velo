"""
Lector de ficheros.
Soporta TXT, DOCX y PDF (con texto extraíble).
Las dependencias para DOCX y PDF son opcionales.
"""

import os


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
            return None, "docx", "El documento DOCX no contiene texto extraíble."
        return text, "docx", None
    except Exception as exc:
        return None, "docx", f"Error al leer DOCX: {exc}"


def _read_pdf(filepath):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None, "pdf", "Para leer ficheros PDF, instale PyPDF2: pip install PyPDF2"

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
                "El PDF no contiene texto extraíble (puede ser un documento escaneado). "
                "Para PDF escaneado haría falta un módulo OCR separado."
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

    try:
        import PyPDF2  # noqa: F401
        formats.append({"ext": ".pdf", "label": "PDF con texto", "available": True})
    except ImportError:
        formats.append({"ext": ".pdf", "label": "PDF (instale PyPDF2)", "available": False})

    return formats
