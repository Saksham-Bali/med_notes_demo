from __future__ import annotations

import re

from models.counselling_fact import CounsellingFact

DIAGNOSIS_PATTERNS = (
    re.compile(r"\bdiagnos(?:ed|is|ing)\b", flags=re.IGNORECASE),
    re.compile(r"\b(cancer|carcinoma|tumou?r|leukemia|lymphoma|metastasis)\b", flags=re.IGNORECASE),
)


def validate_counselling_facts(
    facts: list[CounsellingFact],
    transcript: str,
    min_certainty_threshold: float,
    diagnosis_filter_enabled: bool,
) -> list[CounsellingFact]:
    validated: list[CounsellingFact] = []
    normalized_transcript = normalize_text(transcript)

    for fact in facts:
        candidate = fact.model_copy(deep=True)
        candidate.validation_flags = []
        candidate.selectable = True

        if not evidence_exists(candidate.evidence_text, transcript, normalized_transcript):
            candidate.certainty = round(max(candidate.certainty * 0.5, 0.0), 3)
            candidate.validation_flags.append("evidence_not_found_in_transcript")

        if candidate.evidence_end_time < candidate.evidence_start_time:
            candidate.validation_flags.append("invalid_evidence_timestamps")
            continue

        if diagnosis_filter_enabled and (
            contains_diagnosis(candidate.fact) or contains_diagnosis(candidate.evidence_text)
        ):
            candidate.validation_flags.append("diagnosis_filtered")
            continue

        if candidate.certainty < min_certainty_threshold:
            candidate.validation_flags.append("below_certainty_threshold")
            continue

        validated.append(candidate)

    return validated


def evidence_exists(evidence_text: str, transcript: str, normalized_transcript: str | None = None) -> bool:
    if evidence_text and evidence_text in transcript:
        return True
    normalized_evidence = normalize_text(evidence_text)
    if not normalized_evidence:
        return False
    haystack = normalized_transcript or normalize_text(transcript)
    return normalized_evidence in haystack


def contains_diagnosis(text: str) -> bool:
    return any(pattern.search(text) for pattern in DIAGNOSIS_PATTERNS)


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())
