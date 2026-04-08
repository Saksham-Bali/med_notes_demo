from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from typing import Any


EMPTY_SENTINELS = {"", "n/a", "na", "none", "not available", "null", "unknown"}
STOP_WORDS = {
    "and",
    "are",
    "for",
    "from",
    "has",
    "have",
    "her",
    "his",
    "into",
    "not",
    "the",
    "their",
    "them",
    "then",
    "there",
    "this",
    "was",
    "were",
    "with",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, bool | int | float):
        return str(value)
    if isinstance(value, dict):
        parts = [f"{key} {normalize_text(item)}" for key, item in value.items() if item is not None]
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, list | tuple | set):
        return " ".join(part for part in (normalize_text(item) for item in value) if part).strip()
    return str(value).strip()


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return normalize_text(value).casefold() in EMPTY_SENTINELS
    if isinstance(value, dict):
        return not value or all(is_missing(item) for item in value.values())
    if isinstance(value, list | tuple | set):
        return not value or all(is_missing(item) for item in value)
    return False


def split_into_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        items: list[str] = []
        for item in value:
            items.extend(split_into_items(item))
        return [item for item in items if item]
    if isinstance(value, dict):
        name = normalize_text(value.get("name")) if "name" in value else ""
        if name:
            detail = " ".join(
                normalize_text(value.get(key))
                for key in ("dosage", "frequency", "duration")
                if value.get(key) is not None
            ).strip()
            return [" ".join(part for part in (name, detail) if part)]
        return [normalize_text(value)] if normalize_text(value) else []

    text = normalize_text(value)
    if not text:
        return []

    parts = re.split(r"(?:\n+|;\s+|\s+\|\s+)", text)
    return [part.strip(" -\t") for part in parts if normalize_text(part)]


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 2 and token not in STOP_WORDS
    }


def lexical_match(left: str, right: str, min_overlap: int = 2) -> bool:
    left_norm = normalize_text(left).casefold()
    right_norm = normalize_text(right).casefold()
    if not left_norm or not right_norm:
        return False
    if left_norm in right_norm or right_norm in left_norm:
        return True

    left_tokens = tokenize(left_norm)
    right_tokens = tokenize(right_norm)
    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens)
    required_overlap = 1 if len(left_tokens) == 1 else min(min_overlap, len(left_tokens))
    return overlap >= required_overlap


def fact_text(fact: Any) -> str:
    return normalize_text(
        {
            "entity": getattr(fact, "entity", None),
            "entity_type": getattr(fact, "entity_type", None),
            "normalized_value": getattr(fact, "normalized_value", None),
            "evidence": getattr(fact, "evidence", None),
            "source_section": getattr(fact, "source_section", None),
            "metadata": getattr(fact, "metadata", None),
        }
    )


def section_claims(summary: Any) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    fields = (
        "admission_diagnosis",
        "chief_complaint",
        "investigations",
        "treatment_given",
        "condition_at_discharge",
        "follow_up_schedule",
        "brief_summary",
    )
    for field_name in fields:
        raw_value = getattr(summary, field_name, None)
        text = normalize_text(raw_value)
        if not text:
            continue
        for part in re.split(r"(?:\.\s+|\n+)", text):
            claim = normalize_text(part)
            if len(claim) >= 10:
                claims.append({"section": field_name, "claim": claim})
    return claims


def extract_diagnoses(summary: Any) -> list[str]:
    return split_into_items(getattr(summary, "admission_diagnosis", None))


def extract_medications(summary: Any) -> list[str]:
    return split_into_items(getattr(summary, "medications_on_discharge", None))


def extract_demographic_value(summary: Any, *field_names: str) -> str | None:
    demographics = getattr(summary, "patient_demographics", None)
    if not isinstance(demographics, dict):
        return None
    for field_name in field_names:
        value = demographics.get(field_name)
        if not is_missing(value):
            return normalize_text(value)
    return None


def parse_date(value: Any) -> datetime | None:
    text = normalize_text(value)
    if not text:
        return None

    candidates = [text]
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        candidates.append(match.group(0))

    normalized = text.replace("/", "-")
    if normalized != text:
        candidates.append(normalized)

    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def extract_patient_dates(summary: Any) -> tuple[datetime | None, datetime | None]:
    admission = extract_demographic_value(summary, "date_of_admission", "admission_date")
    discharge = extract_demographic_value(summary, "date_of_discharge", "discharge_date")
    return parse_date(admission), parse_date(discharge)


def compute_summary_hash(summary: Any) -> str:
    payload = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else summary
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
