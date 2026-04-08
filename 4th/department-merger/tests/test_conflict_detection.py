from __future__ import annotations

import asyncio
from datetime import date

from agents.conflict_analyzer import ConflictAnalyzer
from agents.conflict_detector import detect_conflicts
from agents.entity_aligner import align_entities
from config import Settings
from models.aligned_entity import ClinicalFact, DeptExtraction


def test_conflicts_are_detected_and_fallback_analysis_adds_guidance() -> None:
    pathology_stage = ClinicalFact(
        entity="Cancer stage",
        category="staging",
        value="Stage IIIB",
        status="confirmed",
        evidence="Biopsy and pathology staging support Stage IIIB disease.",
        source_department="pathology",
        source_document_date=date(2026, 3, 20),
    )
    oncology_stage = ClinicalFact(
        entity="Cancer stage",
        category="staging",
        value="Stage IV",
        status="confirmed",
        evidence="Medical oncology note documents metastatic disease as Stage IV.",
        source_department="oncology",
        source_document_date=date(2026, 3, 22),
    )
    radiology_effusion = ClinicalFact(
        entity="Pleural effusion",
        category="finding",
        value="Present",
        status="active",
        negated=False,
        evidence="CT chest shows a moderate pleural effusion.",
        source_department="radiology",
        source_document_date=date(2026, 3, 24),
    )
    oncology_effusion = ClinicalFact(
        entity="Pleural effusion",
        category="finding",
        value="Absent",
        status="resolved",
        negated=True,
        evidence="Oncology note says there is no pleural effusion on exam.",
        source_department="oncology",
        source_document_date=date(2026, 3, 24),
    )

    aligned = align_entities(
        [
            DeptExtraction(dept="pathology", facts=[pathology_stage]),
            DeptExtraction(dept="oncology", facts=[oncology_stage, oncology_effusion]),
            DeptExtraction(dept="radiology", facts=[radiology_effusion]),
        ]
    )

    detected = detect_conflicts(aligned)
    conflict_types = {conflict.conflict_type for conflict in detected}
    assert "staging" in conflict_types
    assert "status" in conflict_types

    analyzer = ConflictAnalyzer(Settings())
    analyzed = asyncio.run(analyzer.analyze_many(detected))

    stage_conflict = next(conflict for conflict in analyzed if conflict.conflict_type == "staging")
    assert stage_conflict.severity == "critical"
    assert stage_conflict.authoritative_department == "pathology"
    assert "clinician review" in stage_conflict.suggested_resolution.lower()
