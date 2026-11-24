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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al leer TXT: %s", type(exc).__name__, exc_info=True)
        return None, "txt", "No se pudo leer el fichero de texto."


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Preflight DOCX fallido: %s", type(exc).__name__, exc_info=True)
        return False, "No se pudo inspeccionar el DOCX de forma segura."

    return True, None


# --- DOCX ------------------------------------------------------------------
#
# Hasta la 0.5.x solo se leían ``doc.paragraphs`` (párrafos del cuerpo). Los
# datos personales en tablas, encabezados, pies de página, notas al pie o al
# final, comentarios y cuadros de texto no llegaban al detector, de modo que
# el informe daba una falsa sensación de exhaustividad. Ahora se recorren
# todos los párrafos de cada parte de texto del paquete.

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_W_P = f"{{{_W_NS}}}p"
_W_T = f"{{{_W_NS}}}t"
_W_TAB = f"{{{_W_NS}}}tab"
_W_BR = f"{{{_W_NS}}}br"
_W_CR = f"{{{_W_NS}}}cr"
_MC_FALLBACK = f"{{{_MC_NS}}}Fallback"

# Partes secundarias con texto, en el orden en que se añaden tras el cuerpo.
_DOCX_TEXT_PARTS = (
    ("header", "wordprocessingml.header+xml"),
    ("footer", "wordprocessingml.footer+xml"),
    ("footnotes", "wordprocessingml.footnotes+xml"),
    ("endnotes", "wordprocessingml.endnotes+xml"),
    ("comments", "wordprocessingml.comments+xml"),
)


def _safe_xml(blob: bytes):
    from lxml import etree

    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
    )
    return etree.fromstring(blob, parser=parser)


def _part_root(part):
    element = getattr(part, "element", None)
    if element is not None:
        return element
    return _safe_xml(part.blob)


def _paragraph_text(paragraph) -> str:
    parts: list[str] = []

    def walk(element):
        for child in element:
            tag = child.tag
            if tag in (_W_P, _MC_FALLBACK):
                # Los párrafos anidados (cuadros de texto) se tratan aparte y
                # mc:Fallback duplica en VML el contenido de mc:Choice.
                continue
            if tag == _W_T:
                parts.append(child.text or "")
            elif tag == _W_TAB:
                parts.append("\t")
            elif tag in (_W_BR, _W_CR):
                parts.append("\n")
            else:
                walk(child)

    walk(paragraph)
    return "".join(parts)


def _paragraphs_from_root(root) -> list[str]:
    texts = []
    for paragraph in root.iter(_W_P):
        if any(anc.tag == _MC_FALLBACK for anc in paragraph.iterancestors()):
            continue
        text = _paragraph_text(paragraph)
        if text.strip():
            texts.append(text)
    return texts


def _docx_parts_by_kind(document) -> dict[str, list]:
    found: dict[str, list] = {kind: [] for kind, _ in _DOCX_TEXT_PARTS}
    for part in document.part.package.iter_parts():
        content_type = getattr(part, "content_type", "") or ""
        for kind, suffix in _DOCX_TEXT_PARTS:
            if content_type.endswith(suffix):
                found[kind].append(part)
    for parts in found.values():
        parts.sort(key=lambda item: str(item.partname))
    return found


def extract_docx_text(document) -> str:
    """Texto completo de un ``docx.Document``: cuerpo y partes secundarias."""
    blocks = _paragraphs_from_root(document.element.body)
    for parts in _docx_parts_by_kind(document).values():
        for part in parts:
            blocks.extend(_paragraphs_from_root(_part_root(part)))
    return "\n\n".join(blocks)


def docx_review_notes(filepath: str) -> list[str]:
    """Avisos sobre contenido del DOCX que Velo no puede revisar por sí solo."""
    try:
        from docx import Document

        document = Document(filepath)
    except Exception:  # noqa: BLE001
        return []

    notes: list[str] = []
    body = document.element.body
    if body.find(f".//{{{_W_NS}}}del") is not None or body.find(f".//{{{_W_NS}}}ins") is not None:
        notes.append(
            "El DOCX contiene control de cambios. El texto eliminado con control de "
            "cambios no se analiza, pero sigue dentro del fichero original: "
            "acepte o rechace los cambios antes de difundirlo."
        )
    parts = _docx_parts_by_kind(document)
    if parts["comments"]:
        notes.append(
            "El DOCX contiene comentarios. Se han analizado, pero conservan autor e "
            "iniciales en el fichero original."
        )
    images = sum(
        1 for rel in document.part.rels.values() if str(getattr(rel, "reltype", "")).endswith("/image")
    )
    if images:
        notes.append(
            f"El DOCX contiene {images} imagen(es). Velo no analiza el contenido de "
            "imágenes incrustadas (firmas, sellos, documentos escaneados): revíselas visualmente."
        )
    return notes


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
        text = extract_docx_text(doc)
        if not text.strip():
            return None, "docx", "El documento DOCX no contiene texto extraíble."
        return text, "docx", None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al leer DOCX: %s", type(exc).__name__, exc_info=True)
        return None, "docx", "No se pudo leer el DOCX: el fichero parece dañado o no es un documento Word válido."


def _read_pdf(filepath: str):
    text, fmt, error = _read_pdf_fitz(filepath)
    if error and "motor alternativo" in (error or "").lower():
        logger.info("PyMuPDF no disponible, intentando pypdf como fallback")
        return _read_pdf_pypdf(filepath)
    return text, fmt, error


def _read_pdf_fitz(filepath: str):
    try:
        import pymupdf as fitz
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al leer PDF con PyMuPDF: %s", type(exc).__name__, exc_info=True)
        return None, "pdf", "No se pudo leer el PDF: el fichero parece dañado, cifrado o no es un PDF válido."


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al leer PDF con pypdf: %s", type(exc).__name__, exc_info=True)
        return None, "pdf", "No se pudo leer el PDF: el fichero parece dañado, cifrado o no es un PDF válido."


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
        import pymupdf  # noqa: F401
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
