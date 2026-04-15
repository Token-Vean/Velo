
"""Herramientas para revision visual y aplicacion de redacciones sobre PDFs.

Genera una representacion por paginas del PDF original, extrae palabras con
coordenadas a partir de la capa de texto y, cuando no existe, intenta OCR
sobre la imagen renderizada. Toda la informacion se guarda en una sesion
local efimera para permitir la revision visual, la aplicacion efectiva de las
redacciones sobre una copia del original y la exportacion posterior.

Estrategia de extraccion (v0.3.1):
  - Paginas con capa de texto: se usa get_text("text") como texto canonico
    de alta calidad para el detector, y get_text("words") unicamente para
    obtener los bboxes necesarios para la redaccion visual. Los bboxes se
    alinean contra el texto canonico mediante busqueda secuencial.
  - Paginas con OCR (sin capa de texto): se reconstruye el texto a partir
    de las palabras OCR, que son la unica fuente disponible.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from collections import defaultdict
from itertools import groupby
from typing import Dict, Iterable, List, Tuple

logger = logging.getLogger("velo.visual")

# Proteccion contra bombas de descompresion
try:
    from PIL import Image as _PilImage
    _PilImage.MAX_IMAGE_PIXELS = 25_000_000  # ~5000x5000
except ImportError:
    pass

MAX_PDF_PAGES_VISUAL = 500

TEXT_RENDER_SCALE = 2.0
SESSION_METADATA = "visual.json"
APPLIED_METADATA = "applied_original.json"
APPLIED_PDF_NAME = "original_redacted.pdf"


def visual_capabilities() -> dict:
    caps = {
        "fitz": False,
        "pillow": False,
        "pytesseract": False,
        "tesseract_ready": False,
    }
    try:
        import fitz  # noqa: F401
        caps["fitz"] = True
    except Exception:
        pass
    try:
        from PIL import Image  # noqa: F401
        caps["pillow"] = True
    except Exception:
        pass
    try:
        import pytesseract  # noqa: F401
        caps["pytesseract"] = True
        try:
            import pytesseract as _pt
            _pt.get_tesseract_version()
            caps["tesseract_ready"] = True
        except Exception:
            caps["tesseract_ready"] = False
    except Exception:
        pass
    return caps


def _ensure_dirs(session_dir: str) -> str:
    assets_dir = os.path.join(session_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    return assets_dir


def _render_page_image(page, image_path: str, scale: float = TEXT_RENDER_SCALE) -> Tuple[int, int]:
    import fitz

    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    pix.save(image_path)
    return int(pix.width), int(pix.height)


# ---------------------------------------------------------------------------
# Normalizacion y limpieza de texto
# ---------------------------------------------------------------------------

def _normalize_word(word: str) -> str:
    return " ".join((word or "").replace("\u00a0", " ").split())


def _clean_extracted_text(text: str) -> str:
    """Normaliza Unicode y limpia caracteres problematicos del texto extraido."""
    # Normalizar a NFC (forma compuesta canonica)
    text = unicodedata.normalize("NFC", text)
    # Reemplazar espacios Unicode exoticos por espacio normal
    text = re.sub(r'[\u00a0\u2002\u2003\u2009\u200a\u202f]', ' ', text)
    # Eliminar caracteres de control (excepto \n y \t)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


# ---------------------------------------------------------------------------
# Deteccion y correccion de capas OCR caracter-por-caracter
# ---------------------------------------------------------------------------

def _is_char_level_ocr(raw_words: list) -> bool:
    """Detecta si la capa de texto fue generada caracter por caracter."""
    if len(raw_words) < 10:
        return False
    single_chars = sum(1 for w in raw_words if len(w.get("text", "")) == 1)
    ratio = single_chars / len(raw_words)
    if ratio > 0.40:
        logger.info(
            "Detectada capa OCR caracter-por-caracter (%.0f%% tokens de 1 char)",
            ratio * 100,
        )
        return True
    return False


def _merge_char_level_words(words: List[dict], scale: float) -> List[dict]:
    """Fusiona caracteres sueltos en palabras reales."""
    if not words:
        return words

    merged: List[dict] = []
    for _key, group in groupby(words, key=lambda w: w["line_key"]):
        line_words = list(group)
        if len(line_words) < 2:
            merged.extend(line_words)
            continue

        avg_h = sum(w["bbox"][3] - w["bbox"][1] for w in line_words) / len(line_words)
        gap_threshold = avg_h * 0.40

        current = dict(line_words[0])
        current["bbox"] = list(current["bbox"])

        for nxt in line_words[1:]:
            gap = nxt["bbox"][0] - current["bbox"][2]
            if gap < gap_threshold:
                current["text"] += nxt["text"]
                current["bbox"][2] = nxt["bbox"][2]
                current["bbox"][1] = min(current["bbox"][1], nxt["bbox"][1])
                current["bbox"][3] = max(current["bbox"][3], nxt["bbox"][3])
            else:
                merged.append(current)
                current = dict(nxt)
                current["bbox"] = list(current["bbox"])

        merged.append(current)

    for idx, word in enumerate(merged):
        word["word_no"] = idx

    logger.info(
        "Fusion de caracteres: %d fragmentos -> %d palabras",
        len(words), len(merged),
    )
    return merged


# ---------------------------------------------------------------------------
# Extraccion de palabras (bboxes)
# ---------------------------------------------------------------------------

def _words_from_text_layer(page, scale: float) -> List[dict]:
    words = []
    for item in page.get_text("words", sort=True):
        if len(item) < 8:
            continue
        x0, y0, x1, y1, text, block_no, line_no, word_no = item[:8]
        text = _normalize_word(text)
        if not text:
            continue
        words.append(
            {
                "text": text,
                "bbox": [round(x0 * scale, 2), round(y0 * scale, 2), round(x1 * scale, 2), round(y1 * scale, 2)],
                "block_no": int(block_no),
                "line_no": int(line_no),
                "word_no": int(word_no),
                "line_key": f"{int(block_no)}-{int(line_no)}",
                "source": "text_layer",
            }
        )

    # Detectar y corregir capas OCR caracter-por-caracter
    if _is_char_level_ocr(words):
        words = _merge_char_level_words(words, scale)

    return words


def _words_from_ocr(image_path: str) -> List[dict]:
    from PIL import Image
    import pytesseract
    from pytesseract import Output

    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    words = []
    count = len(data.get("text", []))
    for idx in range(count):
        text = _normalize_word(data["text"][idx])
        if not text:
            continue
        conf_raw = str(data.get("conf", [""])[idx]).strip()
        try:
            conf = float(conf_raw)
        except Exception:
            conf = -1.0
        if conf >= 0 and conf < 25:
            continue
        x = int(data["left"][idx])
        y = int(data["top"][idx])
        w = int(data["width"][idx])
        h = int(data["height"][idx])
        line_key = f"{data.get('block_num', [0])[idx]}-{data.get('par_num', [0])[idx]}-{data.get('line_num', [0])[idx]}"
        words.append(
            {
                "text": text,
                "bbox": [x, y, x + w, y + h],
                "block_no": int(data.get("block_num", [0])[idx] or 0),
                "line_no": int(data.get("line_num", [0])[idx] or 0),
                "word_no": idx,
                "line_key": line_key,
                "source": "ocr",
            }
        )
    return words


# ---------------------------------------------------------------------------
# Mapeo de palabras contra texto canonico (doble extraccion)
# ---------------------------------------------------------------------------

def _map_words_to_canonical(
    words: List[dict],
    canonical_text: str,
    global_offset: int,
    page_number: int,
) -> List[dict]:
    """Asigna a cada palabra su posicion (start/end) dentro del texto canonico.

    Recorre las palabras en orden y busca cada una secuencialmente en el
    texto canonico.  Aplica la misma normalizacion Unicode al texto de cada
    palabra que se aplico al texto canonico para evitar desajustes por NFC,
    caracteres de control, o espacios Unicode exoticos.

    Retorna la lista de palabras mapeadas.  Si el ratio de exito es bajo
    la funcion que llama debera usar el fallback de reconstruccion.
    """
    mapped: List[dict] = []
    scan_pos = 0  # cursor dentro de canonical_text

    canonical_lower = canonical_text.lower()

    for word in words:
        # Normalizar texto de la palabra igual que el canonico
        w_text = _clean_extracted_text(word["text"])
        if not w_text.strip():
            continue

        # 1. Busqueda exacta hacia adelante
        pos = canonical_text.find(w_text, scan_pos)

        # 2. Fallback: case-insensitive
        if pos == -1:
            pos = canonical_lower.find(w_text.lower(), scan_pos)

        # 3. Fallback: busqueda desde el inicio (por si el orden difiere)
        if pos == -1 and scan_pos > 0:
            pos = canonical_text.find(w_text, 0)
            if pos != -1 and pos < scan_pos:
                # Encontrada antes del cursor: aceptar sin avanzar cursor
                start = global_offset + pos
                end = start + len(w_text)
                mapped.append(
                    {
                        "text": w_text,
                        "bbox": word["bbox"],
                        "start": start,
                        "end": end,
                        "line_key": word["line_key"],
                        "page": page_number,
                        "source": word["source"],
                    }
                )
                # NO avanzar scan_pos — fue un match fuera de orden
                continue

        if pos == -1:
            logger.debug(
                "Pag %d: palabra no mapeada: %r (scan_pos=%d/%d)",
                page_number, w_text[:30], scan_pos, len(canonical_text),
            )
            continue

        start = global_offset + pos
        end = start + len(w_text)

        mapped.append(
            {
                "text": w_text,
                "bbox": word["bbox"],
                "start": start,
                "end": end,
                "line_key": word["line_key"],
                "page": page_number,
                "source": word["source"],
            }
        )
        scan_pos = pos + len(w_text)

    return mapped


# ---------------------------------------------------------------------------
# Reconstruccion de texto a partir de palabras (fallback para OCR)
# ---------------------------------------------------------------------------

def _page_text_and_map(words: Iterable[dict], global_offset: int, page_number: int) -> Tuple[str, List[dict], int]:
    """Reconstruye texto a partir de palabras individuales.

    Se usa SOLO para paginas procesadas con OCR propio, donde no existe
    un texto canonico de PyMuPDF. Para paginas con capa de texto se usa
    _map_words_to_canonical en su lugar.
    """
    page_words: List[dict] = []
    text_parts: List[str] = []
    cursor = global_offset
    prev_line_key = None

    for item in words:
        if prev_line_key is None:
            pass
        elif item["line_key"] != prev_line_key:
            text_parts.append("\n")
            cursor += 1
        else:
            text_parts.append(" ")
            cursor += 1

        start = cursor
        text_parts.append(item["text"])
        cursor += len(item["text"])
        end = cursor

        page_words.append(
            {
                "text": item["text"],
                "bbox": item["bbox"],
                "start": start,
                "end": end,
                "line_key": item["line_key"],
                "page": page_number,
                "source": item["source"],
            }
        )
        prev_line_key = item["line_key"]

    return "".join(text_parts), page_words, cursor


# ---------------------------------------------------------------------------
# Funcion principal de procesamiento visual de PDF
# ---------------------------------------------------------------------------

def read_pdf_for_visual_review(filepath: str, session_dir: str, session_id: str) -> Tuple[str, str, str | None, dict | None]:
    caps = visual_capabilities()
    if not caps["fitz"]:
        logger.warning("Revision visual no disponible: falta PyMuPDF (fitz)")
        return None, "pdf", "La revision visual de PDF requiere PyMuPDF (fitz).", None

    import fitz

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    logger.info("Procesando PDF: %.1f MB, sesion=%s", file_size_mb, session_id)

    assets_dir = _ensure_dirs(session_dir)
    document = fitz.open(filepath)
    if document.page_count > MAX_PDF_PAGES_VISUAL:
        logger.warning(
            "PDF rechazado por exceso de paginas: %d (max: %d), tamanio=%.1f MB, sesion=%s",
            document.page_count, MAX_PDF_PAGES_VISUAL, file_size_mb, session_id,
        )
        document.close()
        return None, "pdf", f"PDF con {document.page_count} paginas. Maximo: {MAX_PDF_PAGES_VISUAL}.", None

    logger.info("PDF abierto: %d paginas, %.1f MB, sesion=%s", document.page_count, file_size_mb, session_id)
    pages = []
    parts: List[str] = []
    global_offset = 0
    any_text = False
    used_ocr = False
    used_text_layer = False

    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        image_name = f"page_{page_index + 1:03d}.png"
        image_path = os.path.join(assets_dir, image_name)
        width, height = _render_page_image(page, image_path, TEXT_RENDER_SCALE)

        # ---------------------------------------------------------------
        # Intentar capa de texto nativa (doble extraccion)
        # ---------------------------------------------------------------
        page_words_raw = _words_from_text_layer(page, TEXT_RENDER_SCALE)
        source = "text_layer"

        page_text_start = global_offset
        mapped_words: List[dict] = []
        page_text = ""

        if page_words_raw:
            used_text_layer = True
            any_text = True

            # Texto canonico: alta calidad, flujo natural
            canonical = _clean_extracted_text(page.get_text("text") or "")
            canonical = canonical.strip()

            use_canonical = False

            if canonical:
                # Intentar ruta principal: texto canonico + mapeo de bboxes
                trial_mapped = _map_words_to_canonical(
                    page_words_raw, canonical, global_offset, page_index + 1,
                )
                map_ratio = len(trial_mapped) / len(page_words_raw) if page_words_raw else 0

                if map_ratio >= 0.50:
                    # Mapeo aceptable: usar texto canonico
                    use_canonical = True
                    mapped_words = trial_mapped
                    page_text = canonical
                    global_offset += len(canonical)

                    unmapped = len(page_words_raw) - len(mapped_words)
                    if unmapped > 0:
                        logger.info(
                            "Pagina %d: %d/%d palabras mapeadas al texto canonico "
                            "(%d sin mapear, ratio=%.0f%%)",
                            page_index + 1, len(mapped_words),
                            len(page_words_raw), unmapped, map_ratio * 100,
                        )
                else:
                    # Mapeo insuficiente: fallback a reconstruccion por palabras
                    logger.warning(
                        "Pagina %d: mapeo canonico insuficiente (%d/%d = %.0f%%). "
                        "Usando reconstruccion por palabras para garantizar "
                        "cobertura de redaccion.",
                        page_index + 1, len(trial_mapped),
                        len(page_words_raw), map_ratio * 100,
                    )

            if not use_canonical:
                # Reconstruir texto desde palabras (fallback seguro)
                page_text, mapped_words, global_offset = _page_text_and_map(
                    page_words_raw, global_offset, page_index + 1,
                )

            parts.append(page_text)
            if page_index < document.page_count - 1:
                parts.append("\n\n")
                global_offset += 2

        # ---------------------------------------------------------------
        # Sin capa de texto: intentar OCR
        # ---------------------------------------------------------------
        elif caps["pytesseract"] and caps["tesseract_ready"]:
            ocr_words = _words_from_ocr(image_path)
            source = "ocr"
            used_ocr = True

            if ocr_words:
                any_text = True
                page_text, mapped_words, global_offset = _page_text_and_map(
                    ocr_words, global_offset, page_index + 1,
                )
                parts.append(page_text)
                if page_index < document.page_count - 1:
                    parts.append("\n\n")
                    global_offset += 2
        else:
            source = "none"

        pages.append(
            {
                "page": page_index + 1,
                "image_url": f"/api/session/{session_id}/asset/{image_name}",
                "image_name": image_name,
                "width": width,
                "height": height,
                "text_start": page_text_start,
                "text_end": global_offset,
                "source": source,
                "words": mapped_words,
            }
        )

    document.close()

    if not any_text:
        logger.warning(
            "PDF sin texto extraible: %d paginas, %.1f MB, sesion=%s. "
            "Sugerencia: instalar Tesseract OCR.",
            document.page_count, file_size_mb, session_id,
        )
        return (
            None,
            "pdf",
            "No se ha podido obtener texto ni coordenadas del PDF original. "
            "Instale Tesseract OCR para PDF escaneados.",
            None,
        )

    text = "".join(parts)
    logger.info(
        "PDF procesado correctamente: %d paginas, %d caracteres, modo=%s, sesion=%s",
        len(pages), len(text),
        "hybrid" if used_ocr and used_text_layer else ("ocr" if used_ocr else "text_layer"),
        session_id,
    )
    metadata = {
        "session_id": session_id,
        "pages": pages,
        "page_count": len(pages),
        "ocr_used": used_ocr,
        "text_layer_used": used_text_layer,
        "mode": "hybrid" if used_ocr and used_text_layer else ("ocr" if used_ocr else "text_layer"),
        "original_pdf": os.path.basename(filepath),
    }

    metadata_path = os.path.join(session_dir, SESSION_METADATA)
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)

    return text, "pdf", None, metadata


# ---------------------------------------------------------------------------
# Carga de metadatos de sesion
# ---------------------------------------------------------------------------

def load_session_metadata(session_dir: str) -> dict:
    with open(os.path.join(session_dir, SESSION_METADATA), "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_applied_metadata(session_dir: str) -> dict:
    with open(os.path.join(session_dir, APPLIED_METADATA), "r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Aplicacion de redacciones visuales
# ---------------------------------------------------------------------------

def _rectangles_for_page(page_meta: dict, confirmed_findings: List[dict]) -> List[List[float]]:
    per_group: Dict[Tuple[str, str], List[List[float]]] = defaultdict(list)
    words = page_meta.get("words", [])
    for finding in confirmed_findings:
        start = finding.get("position", {}).get("start")
        end = finding.get("position", {}).get("end")
        fid = finding.get("id")
        if start is None or end is None:
            continue
        overlaps = [w for w in words if not (end <= w["start"] or start >= w["end"])]
        for word in overlaps:
            per_group[(fid, word["line_key"])].append(word["bbox"])

    rectangles = []
    for boxes in per_group.values():
        x0 = min(box[0] for box in boxes)
        y0 = min(box[1] for box in boxes)
        x1 = max(box[2] for box in boxes)
        y1 = max(box[3] for box in boxes)
        rectangles.append([max(0, x0 - 2), max(0, y0 - 1), x1 + 2, y1 + 1])
    return rectangles


def _confirmed_findings(findings: List[dict]) -> List[dict]:
    return [item for item in findings if item.get("status") == "confirmed"]


def _signature_for_findings(findings: List[dict]) -> str:
    payload = []
    for item in sorted(_confirmed_findings(findings), key=lambda x: (x.get("id", ""), x.get("position", {}).get("start", -1))):
        payload.append(
            {
                "id": item.get("id"),
                "start": item.get("position", {}).get("start"),
                "end": item.get("position", {}).get("end"),
                "technique": item.get("technique"),
                "status": item.get("status"),
            }
        )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_pdf_from_images(image_paths: List[str], output_path: str) -> None:
    """Compone el PDF final con PyMuPDF a partir de PNGs ya redactados.

    Esto evita los fallos intermitentes observados al guardar PDFs multiimagen
    directamente con Pillow en algunos entornos Windows.
    """
    import fitz
    from PIL import Image

    if not image_paths:
        raise ValueError("No hay imagenes redactadas para componer el PDF final.")

    pdf = fitz.open()
    try:
        for image_path in image_paths:
            with Image.open(image_path) as image:
                width, height = image.size

            page = pdf.new_page(width=float(width), height=float(height))
            page.insert_image(page.rect, filename=image_path)
        pdf.save(output_path, garbage=4, deflate=True)
    finally:
        pdf.close()


def apply_redactions_to_original(session_dir: str, session_id: str, findings: List[dict]) -> dict:
    from PIL import Image, ImageDraw

    metadata = load_session_metadata(session_dir)
    confirmed = _confirmed_findings(findings)
    if not confirmed:
        raise ValueError("No hay hallazgos confirmados para aplicar sobre el original.")

    assets_dir = _ensure_dirs(session_dir)
    page_results = []
    redacted_paths: List[str] = []
    total_rectangles = 0

    for page_meta in metadata.get("pages", []):
        image_path = os.path.join(assets_dir, page_meta["image_name"])
        rectangles = _rectangles_for_page(page_meta, confirmed)

        with Image.open(image_path) as base_image:
            image = base_image.convert("RGB")
            draw = ImageDraw.Draw(image)
            for rect in rectangles:
                draw.rectangle(rect, fill="black")

            redacted_name = f"redacted_{page_meta['image_name']}"
            redacted_path = os.path.join(assets_dir, redacted_name)
            image.save(redacted_path)
            image.close()

        redacted_paths.append(redacted_path)
        total_rectangles += len(rectangles)
        page_results.append(
            {
                "page": page_meta["page"],
                "image_url": f"/api/session/{session_id}/asset/{redacted_name}",
                "image_name": redacted_name,
                "width": page_meta["width"],
                "height": page_meta["height"],
                "rectangles": len(rectangles),
            }
        )

    if not redacted_paths:
        raise ValueError("No hay paginas renderizadas para aplicar las redacciones.")

    output_path = os.path.join(session_dir, APPLIED_PDF_NAME)
    _build_pdf_from_images(redacted_paths, output_path)

    applied = {
        "session_id": session_id,
        "pdf_url": f"/api/session/{session_id}/applied-original-pdf",
        "pdf_name": APPLIED_PDF_NAME,
        "pages": page_results,
        "page_count": len(page_results),
        "total_rectangles": total_rectangles,
        "findings_signature": _signature_for_findings(findings),
        "based_on_original_pdf_images": True,
    }
    with open(os.path.join(session_dir, APPLIED_METADATA), "w", encoding="utf-8") as handle:
        json.dump(applied, handle, ensure_ascii=False, indent=2)
    return applied


def export_visual_redacted_pdf(session_dir: str, findings: List[dict], output_path: str) -> str:
    result = apply_redactions_to_original(session_dir, "export", findings)
    generated = os.path.join(session_dir, APPLIED_PDF_NAME)
    if os.path.abspath(generated) != os.path.abspath(output_path):
        with open(generated, "rb") as src, open(output_path, "wb") as dst:
            dst.write(src.read())
    return output_path
