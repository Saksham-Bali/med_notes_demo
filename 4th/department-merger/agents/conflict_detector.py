from __future__ import annotations

from datetime import date

from models.aligned_entity import AlignedEntity, ClinicalFact
from models.conflict import Conflict, ConflictFactSnapshot


def detect_conflicts(aligned_entities: list[AlignedEntity]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    seen: set[tuple[str, str, str, str]] = set()

    for entity in aligned_entities:
        facts = entity.facts
        for index, fact_a in enumerate(facts):
            for fact_b in facts[index + 1 :]:
                if fact_a.source_department == fact_b.source_department:
                    continue

                for conflict_type, description in _pairwise_conflicts(entity.canonical_name, fact_a, fact_b):
                    signature = (
                        entity.normalized_key,
                        conflict_type,
                        "|".join(sorted([fact_a.source_department or "", fact_b.source_department or ""])),
                        description,
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    conflicts.append(
                        Conflict(
                            entity=entity.canonical_name,
                            conflict_type=conflict_type,
                            department_a=fact_a.source_department or "unknown",
                            department_b=fact_b.source_department or "unknown",
                            description=description,
                            severity=_assess_severity(conflict_type, fact_a, fact_b),
                            fact_a=_snapshot(fact_a),
                            fact_b=_snapshot(fact_b),
                        )
                    )

    return conflicts


def _pairwise_conflicts(
    entity_name: str,
    fact_a: ClinicalFact,
    fact_b: ClinicalFact,
) -> list[tuple[str, str]]:
    conflicts: list[tuple[str, str]] = []
    entity_lower = entity_name.lower()

    if fact_a.status and fact_b.status and _normalize(fact_a.status) != _normalize(fact_b.status):
        conflicts.append(
            (
                "status",
                f"{fact_a.source_department} marks {entity_name} as {fact_a.status}, while "
                f"{fact_b.source_department} marks it as {fact_b.status}.",
            )
        )

    if fact_a.negated != fact_b.negated:
        polarity_a = "negates" if fact_a.negated else "asserts"
        polarity_b = "negates" if fact_b.negated else "asserts"
        conflicts.append(
            (
                "status",
                f"{fact_a.source_department} {polarity_a} {entity_name}, while "
                f"{fact_b.source_department} {polarity_b} it.",
            )
        )

    if fact_a.value and fact_b.value and _normalize(fact_a.value) != _normalize(fact_b.value):
        conflict_type = _value_conflict_type(entity_lower, fact_a, fact_b)
        conflicts.append(
            (
                conflict_type,
                f"{fact_a.source_department} records {entity_name} as '{fact_a.value}', while "
                f"{fact_b.source_department} records it as '{fact_b.value}'.",
            )
        )

    fact_a_date = fact_a.date or fact_a.source_document_date
    fact_b_date = fact_b.date or fact_b.source_document_date
    if fact_a_date and fact_b_date:
        day_gap = abs((fact_a_date - fact_b_date).days)
        if day_gap >= 30:
            conflicts.append(
                (
                    "date",
                    f"{entity_name} appears with materially different dates: "
                    f"{fact_a.source_department} cites {fact_a_date.isoformat()} and "
                    f"{fact_b.source_department} cites {fact_b_date.isoformat()}.",
                )
            )

    return conflicts


def _value_conflict_type(
    entity_lower: str,
    fact_a: ClinicalFact,
    fact_b: ClinicalFact,
) -> str:
    category_text = " ".join(
        filter(
            None,
            [
                fact_a.category.lower() if fact_a.category else None,
                fact_b.category.lower() if fact_b.category else None,
                entity_lower,
            ],
        )
    )
    if any(keyword in category_text for keyword in {"medication", "drug", "analgesic", "dose", "regimen"}):
        return "medication"
    if any(keyword in category_text for keyword in {"stage", "staging", "tnm"}):
        return "staging"
    return "other"


def _assess_severity(conflict_type: str, fact_a: ClinicalFact, fact_b: ClinicalFact) -> str:
    if conflict_type == "staging":
        return "critical"
    if conflict_type == "medication":
        return "critical" if fact_a.negated != fact_b.negated else "moderate"
    if conflict_type == "status":
        return "moderate"
    if conflict_type == "date":
        fact_a_date = fact_a.date or fact_a.source_document_date
        fact_b_date = fact_b.date or fact_b.source_document_date
        if fact_a_date and fact_b_date and abs((fact_a_date - fact_b_date).days) >= 90:
            return "moderate"
        return "minor"
    return "minor"


def _snapshot(fact: ClinicalFact) -> ConflictFactSnapshot:
    return ConflictFactSnapshot(
        department=fact.source_department or "unknown",
        author=fact.source_author,
        document_date=fact.source_document_date or fact.date,
        value=fact.value,
        status=fact.status,
        negated=fact.negated,
        evidence=fact.evidence,
        radlex_id=fact.radlex_id,
    )


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())
