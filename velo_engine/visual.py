"""Herramientas para revisión visual y aplicación de redacciones sobre PDFs.

Genera una representación por páginas del PDF original, extrae palabras con
coordenadas a partir de la capa de texto y, cuando no existe, intenta OCR
sobre la imagen renderizada. Toda la información se guarda en una sesión
local efímera para permitir la revisión visual, la aplicación efectiva de las
redacciones sobre una copia del original y la exportación posterior.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

# Proteccion contra bombas de descompresion
try:
    from PIL import Image as _PilImage
    _PilImage.MAX_IMAGE_PIXELS = 25_000_000  # ~5000x5000
except ImportError:
    pass

MAX_PDF_PAGES_VISUAL = 100


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


def _normalize_word(word: str) -> str:
    return " ".join((word or "").replace(" ", " ").split())


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


def _page_text_and_map(words: Iterable[dict], global_offset: int, page_number: int) -> Tuple[str, List[dict], int]:
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


def read_pdf_for_visual_review(filepath: str, session_dir: str, session_id: str) -> Tuple[str, str, str | None, dict | None]:
    caps = visual_capabilities()
    if not caps["fitz"]:
        return None, "pdf", "La revisión visual de PDF requiere PyMuPDF (fitz).", None

    import fitz

    assets_dir = _ensure_dirs(session_dir)
    document = fitz.open(filepath)
    if document.page_count > MAX_PDF_PAGES_VISUAL:
        document.close()
        return None, "pdf", f"PDF con {document.page_count} paginas. Maximo: {MAX_PDF_PAGES_VISUAL}.", None
    pages = []
    parts: List[str] = []
    global_offset = 0
    any_words = False
    used_ocr = False
    used_text_layer = False

    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        image_name = f"page_{page_index + 1:03d}.png"
        image_path = os.path.join(assets_dir, image_name)
        width, height = _render_page_image(page, image_path, TEXT_RENDER_SCALE)

        page_words = _words_from_text_layer(page, TEXT_RENDER_SCALE)
        source = "text_layer"
        if page_words:
            used_text_layer = True
        elif caps["pytesseract"] and caps["tesseract_ready"]:
            page_words = _words_from_ocr(image_path)
            source = "ocr"
            used_ocr = True
        else:
            source = "none"

        page_text_start = global_offset
        mapped_words = []
        if page_words:
            any_words = True
            page_text, mapped_words, global_offset = _page_text_and_map(page_words, global_offset, page_index + 1)
            parts.append(page_text)
            if page_index < document.page_count - 1:
                parts.append("\n\n")
                global_offset += 2

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

    if not any_words:
        return (
            None,
            "pdf",
            "No se ha podido obtener texto ni coordenadas del PDF original. Instale Tesseract OCR para PDF escaneados.",
            None,
        )

    text = "".join(parts)
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


def load_session_metadata(session_dir: str) -> dict:
    with open(os.path.join(session_dir, SESSION_METADATA), "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_applied_metadata(session_dir: str) -> dict:
    with open(os.path.join(session_dir, APPLIED_METADATA), "r", encoding="utf-8") as handle:
        return json.load(handle)


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


def apply_redactions_to_original(session_dir: str, session_id: str, findings: List[dict]) -> dict:
    from PIL import Image, ImageDraw

    metadata = load_session_metadata(session_dir)
    confirmed = _confirmed_findings(findings)
    if not confirmed:
        raise ValueError("No hay hallazgos confirmados para aplicar sobre el original.")

    assets_dir = _ensure_dirs(session_dir)
    rendered_pages = []
    page_results = []
    total_rectangles = 0

    for page_meta in metadata.get("pages", []):
        image_path = os.path.join(assets_dir, page_meta["image_name"])
        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        rectangles = _rectangles_for_page(page_meta, confirmed)
        for rect in rectangles:
            draw.rectangle(rect, fill="black")
        redacted_name = f"redacted_{page_meta['image_name']}"
        redacted_path = os.path.join(assets_dir, redacted_name)
        image.save(redacted_path)
        rendered_pages.append(image)
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

    if not rendered_pages:
        raise ValueError("No hay páginas renderizadas para aplicar las redacciones.")

    output_path = os.path.join(session_dir, APPLIED_PDF_NAME)
    first, rest = rendered_pages[0], rendered_pages[1:]
    first.save(output_path, save_all=True, append_images=rest, resolution=150.0)

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
