from __future__ import annotations

import re
from collections import Counter
from datetime import date

from models.aligned_entity import AlignedEntity, ClinicalFact, DeptExtraction, FactProvenance, UnifiedFact
from models.conflict import Conflict


def align_entities(dept_extractions: list[DeptExtraction]) -> list[AlignedEntity]:
    aligned_groups: dict[str, list[ClinicalFact]] = {}

    for extraction in dept_extractions:
        for fact in extraction.facts:
            match_key = _find_matching_group_key(fact, aligned_groups)
            group_key = match_key or _alignment_key(fact)
            aligned_groups.setdefault(group_key, []).append(fact)

    aligned_entities: list[AlignedEntity] = []
    for group_key, facts in sorted(aligned_groups.items(), key=lambda item: item[0]):
        sorted_facts = sorted(facts, key=_fact_sort_key)
        aligned_entities.append(
            AlignedEntity(
                canonical_name=_canonical_name(sorted_facts),
                normalized_key=group_key,
                radlex_id=next((fact.radlex_id for fact in sorted_facts if fact.radlex_id), None),
                facts=sorted_facts,
                departments=sorted(
                    {
                        fact.source_department
                        for fact in sorted_facts
                        if fact.source_department
                    }
                ),
            )
        )

    return aligned_entities


def build_unified_facts(
    aligned_entities: list[AlignedEntity],
    conflicts: list[Conflict],
) -> list[UnifiedFact]:
    conflict_keys = {_normalize_text(conflict.entity) for conflict in conflicts}
    unified_facts: list[UnifiedFact] = []

    for entity in aligned_entities:
        dates = [
            fact.source_document_date or fact.date
            for fact in entity.facts
            if fact.source_document_date or fact.date
        ]
        unified_facts.append(
            UnifiedFact(
                entity=entity.canonical_name,
                canonical_name=entity.canonical_name,
                normalized_key=entity.normalized_key,
                radlex_id=entity.radlex_id,
                category=_most_common([fact.category for fact in entity.facts]),
                value=_latest_non_empty_value(entity.facts),
                statuses=sorted({fact.status for fact in entity.facts if fact.status}),
                negated=_resolve_negation(entity.facts),
                departments=entity.departments,
                provenance=[
                    FactProvenance(
                        department=fact.source_department or "unknown",
                        author=fact.source_author,
                        document_date=fact.source_document_date or fact.date,
                        evidence=fact.evidence,
                        status=fact.status,
                        negated=fact.negated,
                        value=fact.value,
                        confidence=fact.confidence,
                    )
                    for fact in entity.facts
                ],
                fact_count=len(entity.facts),
                latest_document_date=max(dates) if dates else None,
                has_conflict=_normalize_text(entity.canonical_name) in conflict_keys,
            )
        )

    return unified_facts


def should_merge_radlex(candidate: ClinicalFact, reference: ClinicalFact) -> bool:
    if candidate.radlex_id and reference.radlex_id:
        return candidate.radlex_id == reference.radlex_id

    if _normalize_text(candidate.entity) != _normalize_text(reference.entity):
        return False

    if candidate.category and reference.category:
        return _normalize_text(candidate.category) == _normalize_text(reference.category)

    return True


def _find_matching_group_key(
    candidate: ClinicalFact,
    aligned_groups: dict[str, list[ClinicalFact]],
) -> str | None:
    for group_key, group in aligned_groups.items():
        if group and should_merge_radlex(candidate, group[0]):
            return group_key
    return None


def _alignment_key(fact: ClinicalFact) -> str:
    if fact.radlex_id:
        return f"radlex:{fact.radlex_id}"
    return f"name:{_normalize_text(fact.entity)}"


def _canonical_name(facts: list[ClinicalFact]) -> str:
    names = [fact.entity.strip() for fact in facts if fact.entity.strip()]
    if not names:
        return "unknown"

    counts = Counter(names)
    return max(counts, key=lambda item: (counts[item], len(item), item.lower()))


def _most_common(values: list[str | None]) -> str | None:
    filtered = [value for value in values if value]
    if not filtered:
        return None
    counts = Counter(filtered)
    return max(counts, key=lambda item: (counts[item], len(item), item.lower()))


def _latest_non_empty_value(facts: list[ClinicalFact]) -> str | None:
    dated_values: list[tuple[date | None, str]] = []
    for fact in facts:
        if not fact.value:
            continue
        dated_values.append((fact.source_document_date or fact.date, fact.value))
    if not dated_values:
        return None
    dated_values.sort(key=lambda item: (item[0] is None, item[0]))
    return dated_values[-1][1]


def _resolve_negation(facts: list[ClinicalFact]) -> bool | None:
    values = {fact.negated for fact in facts}
    if len(values) == 1:
        return values.pop()
    return None


def _fact_sort_key(fact: ClinicalFact) -> tuple[int, date | None, str]:
    return (
        0 if fact.source_document_date or fact.date else 1,
        fact.source_document_date or fact.date,
        fact.source_department or "",
    )


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower().strip()
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", collapsed).strip()
