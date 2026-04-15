"""
Motor de detección de datos sensibles.
Capa base: regex para patrones estructurados españoles.
Capa opcional: spaCy para NER (nombres, lugares, instituciones).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from velo_engine.constants import APP_VERSION

logger = logging.getLogger("velo.detector")

PATTERNS = [
    {
        "id": "dni",
        "label": "DNI",
        "category": "identification",
        "description": "Documento Nacional de Identidad",
        "regex": r"\b\d{8}[A-HJ-NP-TV-Z]\b",
        "flags": re.IGNORECASE,
    },
    {
        "id": "nie",
        "label": "NIE",
        "category": "identification",
        "description": "Número de Identidad de Extranjero",
        "regex": r"\b[XYZ]\d{7}[A-Z]\b",
        "flags": re.IGNORECASE,
    },
    {
        "id": "nss",
        "label": "Nº Seg. Social",
        "category": "identification",
        "description": "Número de la Seguridad Social",
        "regex": r"\b\d{2}\s*[/-]\s*\d{8,10}\s*[/-]\s*\d{2}\b",
        "flags": 0,
    },
    {
        "id": "phone",
        "label": "Teléfono",
        "category": "contact",
        "description": "Número de teléfono",
        "regex": r"(?:\+34\s*)?\b[6-9]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}\b",
        "flags": 0,
    },
    {
        "id": "email",
        "label": "Email",
        "category": "contact",
        "description": "Dirección de correo electrónico",
        "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "flags": 0,
    },
    {
        "id": "iban",
        "label": "IBAN",
        "category": "financial",
        "description": "Cuenta bancaria IBAN",
        "regex": r"\bES\d{22}\b",
        "flags": re.IGNORECASE,
    },
    {
        "id": "credit_card",
        "label": "Tarjeta",
        "category": "financial",
        "description": "Número de tarjeta de crédito/débito",
        "regex": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}\b",
        "flags": 0,
    },
    {
        "id": "date_birth",
        "label": "Fecha nac.",
        "category": "personal",
        "description": "Fecha de nacimiento",
        "regex": r"(?:nacid[oa]|fecha\s+de\s+nacimiento|f\.?\s*nac\.?|nac\.|nacimiento)\s*:?\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{2,4})",
        "flags": re.IGNORECASE,
    },
    {
        "id": "address",
        "label": "Dirección",
        "category": "contact",
        "description": "Dirección postal",
        "regex": r"\b(?:(?:C|c)(?:alle|/)|Av(?:da|enida)?\.?|Pza?\.?|Plaza|Paseo|Pº\.?|Camino|Cno\.?|Carretera|Ctra\.?)\s+[A-ZÀ-ÿa-z0-9\s]+,?\s*(?:n[ºo°]?\s*)?\d+(?:\s*[-,]\s*\d+[ºªo]?\s*[A-Za-z]?)?",
        "flags": 0,
    },
]

_DNI_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
_SPACY_ERROR: str | None = None


def _normalize_compact(value):
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def _valid_dni(value):
    value = _normalize_compact(value)
    if not re.fullmatch(r"\d{8}[A-Z]", value):
        return False
    return _DNI_TABLE[int(value[:8]) % 23] == value[-1]


def _valid_nie(value):
    value = _normalize_compact(value)
    if not re.fullmatch(r"[XYZ]\d{7}[A-Z]", value):
        return False
    mapped = {"X": "0", "Y": "1", "Z": "2"}[value[0]] + value[1:8]
    return _DNI_TABLE[int(mapped) % 23] == value[-1]


def _valid_iban(value):
    value = _normalize_compact(value)
    if not re.fullmatch(r"ES\d{22}", value):
        return False
    rearranged = value[4:] + value[:4]
    numeric = "".join(ch if ch.isdigit() else str(ord(ch) - 55) for ch in rearranged)
    remainder = 0
    for ch in numeric:
        remainder = (remainder * 10 + int(ch)) % 97
    return remainder == 1


def _valid_luhn(value):
    digits = re.sub(r"\D", "", value or "")
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _validate_match(pattern_id, raw_text):
    if pattern_id == "dni":
        return _valid_dni(raw_text)
    if pattern_id == "nie":
        return _valid_nie(raw_text)
    if pattern_id == "iban":
        return _valid_iban(raw_text)
    if pattern_id == "credit_card":
        return _valid_luhn(raw_text)
    return True


def _overlaps(new_start, new_end, findings):
    for finding in findings:
        start = finding["position"]["start"]
        end = finding["position"]["end"]
        if not (new_end <= start or new_start >= end):
            return True
    return False


def detect_regex(text):
    findings = []
    counter = 0

    for pattern in PATTERNS:
        regex = re.compile(pattern["regex"], pattern["flags"])
        for match in regex.finditer(text):
            raw_text = match.group()
            start, end = match.start(), match.end()

            if not _validate_match(pattern["id"], raw_text):
                continue
            if _overlaps(start, end, findings):
                continue

            counter += 1
            findings.append({
                "id": f"f{counter:03d}",
                "text": raw_text,
                "category": pattern["category"],
                "type": pattern["id"],
                "label": pattern["label"],
                "description": pattern["description"],
                "position": {"start": start, "end": end},
                "confidence": 1.0,
                "method": "regex",
                "status": "pending",
            })

    findings.sort(key=lambda item: item["position"]["start"])
    return findings


def _load_spacy_model():
    global _SPACY_ERROR
    try:
        import spacy  # type: ignore
    except Exception as exc:  # noqa: BLE001
        _SPACY_ERROR = f"{type(exc).__name__}: {exc}"
        logger.warning("spaCy no disponible o no cargable: %s", exc, exc_info=True)
        return None, None

    for model_name in ("es_core_news_md", "es_core_news_sm"):
        try:
            nlp = spacy.load(model_name)
            _SPACY_ERROR = None
            logger.info("Modelo spaCy cargado: %s", model_name)
            return nlp, model_name
        except Exception as exc:  # noqa: BLE001
            _SPACY_ERROR = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "spaCy presente, pero el modelo %s no pudo cargarse: %s",
                model_name,
                exc,
                exc_info=True,
            )
            continue

    return None, None


def detect_ner(text, existing_findings=None):
    if existing_findings is None:
        existing_findings = []
    try:
        nlp, model_name = _load_spacy_model()
        if nlp is None:
            return [], None

        doc = nlp(text)
        findings = []
        counter = len(existing_findings)
        label_map = {
            "PER": ("person_name", "Nombre persona", "personal"),
            "ORG": ("org_name", "Organización", "personal"),
            "LOC": ("location", "Lugar", "contact"),
            "GPE": ("location", "Lugar", "contact"),
        }

        for ent in doc.ents:
            if ent.label_ not in label_map:
                continue
            type_id, label, category = label_map[ent.label_]
            start, end = ent.start_char, ent.end_char
            if _overlaps(start, end, existing_findings + findings):
                continue
            counter += 1
            findings.append({
                "id": f"f{counter:03d}",
                "text": ent.text,
                "category": category,
                "type": type_id,
                "label": label,
                "description": f"Entidad detectada por NER ({ent.label_})",
                "position": {"start": start, "end": end},
                "confidence": round(0.75 + 0.2 * (ent.end - ent.start > 1), 2),
                "method": "spacy_ner",
                "status": "pending",
            })
        return findings, model_name
    except Exception as exc:  # noqa: BLE001
        global _SPACY_ERROR
        _SPACY_ERROR = f"{type(exc).__name__}: {exc}"
        logger.warning("Fallo no fatal en detect_ner; se desactiva spaCy: %s", exc, exc_info=True)
        return [], None


def detect(text):
    findings = detect_regex(text)
    logger.info("Capa regex: %d hallazgos en %d caracteres", len(findings), len(text))
    ner_findings, model_name = detect_ner(text, findings)
    if model_name:
        logger.info("Capa NER (%s): %d hallazgos adicionales", model_name, len(ner_findings))
    findings.extend(ner_findings)
    findings.sort(key=lambda item: item["position"]["start"])

    layers = ["regex"]
    if model_name:
        layers.append("spacy_ner")

    return {
        "findings": findings,
        "layers_active": layers,
        "layers_available": ["regex", "spacy_ner"],
        "spacy_model": model_name,
    }


def spacy_status():
    _, model_name = _load_spacy_model()
    return {"installed": model_name is not None, "model": model_name, "error": _SPACY_ERROR}


def build_envelope(document_id, findings, layers_active, layers_available):
    now = datetime.now().isoformat()
    confirmed = [item for item in findings if item["status"] == "confirmed"]
    discarded = [item for item in findings if item["status"] == "discarded"]

    return {
        "document_id": document_id,
        "analysis_date": now,
        "tool": "velo",
        "version": APP_VERSION,
        "method": "regex+ner" if "spacy_ner" in layers_active else "regex",
        "layers_active": layers_active,
        "layers_available": layers_available,
        "normative_framework": {
            "redaction": "ISO/IEC 27038 - Especificación para tachado digital",
            "anonymization_techniques": "ISO/IEC 20889 - Técnicas de anonimización y seudonimización",
            "reidentification_risk": "ISO/IEC 27559 - Evaluación de riesgo de reidentificación",
            "privacy_framework": "ISO/IEC 29100 - Marco de privacidad",
            "privacy_management": "ISO/IEC 27701 - Gestión de privacidad de la información",
            "note_authentic_documents": "ISO/IEC 23264-1/2 - Referencia. El flujo actual genera una copia nueva y no modifica el original.",
        },
        "findings": [
            {
                "id": item["id"],
                "text": item["text"],
                "category": item["category"],
                "type": item["type"],
                "label": item["label"],
                "position": item["position"],
                "confidence": item["confidence"],
                "method": item["method"],
                "human_decision": "confirmed",
                "technique": item.get("technique", "suppression"),
            }
            for item in confirmed
        ],
        "discarded": [
            {"id": item["id"], "text": item["text"], "type": item["type"], "reason": "false_positive"}
            for item in discarded
        ],
        "summary": {
            "total_detected": len(findings),
            "confirmed": len(confirmed),
            "discarded": len(discarded),
            "categories_found": list({item["category"] for item in confirmed}),
            "types_found": list({item["type"] for item in confirmed}),
        },
        "audit": {
            "reviewed_by": "archivero",
            "review_date": now.split("T")[0],
            "tool_version": APP_VERSION,
            "execution": "local",
            "standards_applied": ["ISO/IEC 27038", "ISO/IEC 20889", "ISO/IEC 27559", "ISO/IEC 29100"],
        },
    }
