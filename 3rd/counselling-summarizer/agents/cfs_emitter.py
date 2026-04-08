from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from models.clinical_fact import ClinicalFact
from models.counselling_fact import CounsellingFact

CATEGORY_PREFIX = {
    "CONCERN": "patient concern",
    "ACTION": "recommended action",
    "DECISION": "clinical decision",
    "EMOTIONAL": "emotional state",
    "FOLLOW_UP": "follow-up item",
}


def emit_clinical_facts(
    counselling_facts: list[CounsellingFact],
    department: str | None,
    emitted_at: datetime | None = None,
) -> list[ClinicalFact]:
    emitted_at = emitted_at or datetime.now(UTC)
    normalized_department = department or "unknown"
    clinical_facts: list[ClinicalFact] = []

    for fact in counselling_facts:
        clinical_facts.append(
            ClinicalFact(
                entity=f"{CATEGORY_PREFIX[fact.category]}: {fact.fact}",
                radlex_id=None,
                entity_type="PRIMARY",
                certainty=fact.certainty,
                evidence=(
                    f"{fact.speaker.title()}: {fact.evidence_text} "
                    f"[{fact.evidence_start_time:.1f}s-{fact.evidence_end_time:.1f}s]"
                ),
                source_type="COUNSELLING",
                source_department=normalized_department,
                timestamp=emitted_at,
                negated=False,
                status="PRESENT",
            )
        )

    return clinical_facts


def build_session_summary(facts: list[CounsellingFact]) -> str:
    if not facts:
        return "No clinically relevant counselling facts were identified in this session."

    grouped: dict[str, list[str]] = defaultdict(list)
    for fact in facts:
        grouped[fact.category].append(fact.fact)

    parts: list[str] = []
    if grouped["CONCERN"]:
        parts.append(f"Patient concerns included {join_phrases(grouped['CONCERN'])}.")
    if grouped["ACTION"]:
        parts.append(f"Recommended actions included {join_phrases(grouped['ACTION'])}.")
    if grouped["DECISION"]:
        parts.append(f"Decisions discussed included {join_phrases(grouped['DECISION'])}.")
    if grouped["EMOTIONAL"]:
        parts.append(f"Emotional context noted {join_phrases(grouped['EMOTIONAL'])}.")
    if grouped["FOLLOW_UP"]:
        parts.append(f"Follow-up commitments included {join_phrases(grouped['FOLLOW_UP'])}.")

    return " ".join(parts)


def join_phrases(items: list[str], limit: int = 2) -> str:
    selected = items[:limit]
    if len(items) > limit:
        selected[-1] = f"{selected[-1]}, and additional related items"
    if len(selected) == 1:
        return selected[0]
    return ", ".join(selected[:-1]) + f", and {selected[-1]}"
