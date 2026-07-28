from __future__ import annotations

from datetime import date

from agents.entity_aligner import align_entities, build_unified_facts
from models.aligned_entity import ClinicalFact, DeptExtraction


def test_align_entities_merges_by_radlex_and_preserves_provenance() -> None:
    oncology_fact = ClinicalFact(
        entity="Lung mass",
        category="finding",
        value="3.2 cm right upper lobe mass",
        status="active",
        radlex_id="RID4271",
        evidence="CT chest shows a right upper lobe lung mass.",
        source_department="oncology",
        source_author="Dr. Rao",
        source_document_date=date(2026, 3, 24),
    )
    radiology_fact = ClinicalFact(
        entity="Right upper lobe lung mass",
        category="finding",
        value="3.2 cm RUL lesion",
        status="active",
        radlex_id="RID4271",
        evidence="PET-CT confirms hypermetabolic right upper lobe lesion.",
        source_department="radiology",
        source_author="Dr. Shah",
        source_document_date=date(2026, 3, 25),
    )

    aligned = align_entities(
        [
            DeptExtraction(dept="oncology", facts=[oncology_fact]),
            DeptExtraction(dept="radiology", facts=[radiology_fact]),
        ]
    )

    assert len(aligned) == 1
    assert aligned[0].radlex_id == "RID4271"
    assert aligned[0].departments == ["oncology", "radiology"]

    unified = build_unified_facts(aligned, [])
    assert len(unified) == 1
    assert unified[0].fact_count == 2
    assert unified[0].has_conflict is False
    assert [item.department for item in unified[0].provenance] == ["oncology", "radiology"]
