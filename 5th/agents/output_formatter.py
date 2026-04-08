from __future__ import annotations

from typing import Any

from models.discharge_summary import DischargeSummary, SummaryContext
from models.request import GenerateSummaryRequest
from models.response import (
    GenerateSummaryResponse,
    GenerateSummaryResult,
    SectionMetadata,
)


class OutputFormatter:
    SECTION_KEYS = {
        "investigations": {
            "laboratory_results",
            "lab_results",
            "labs",
            "imaging_findings",
            "imaging",
            "pathology_results",
            "pathology",
        },
        "treatment": {
            "medications_during_stay",
            "medications",
            "procedures_performed",
            "procedures",
            "chemotherapy_details",
            "radiation_details",
            "treatment",
            "treatments",
        },
        "disease_progression": {
            "measurement_trends",
            "measurements",
            "recist",
            "tumor_response",
            "lesions",
        },
        "counselling": {"counselling", "counseling", "approved_counselling"},
    }

    def format(
        self,
        request: GenerateSummaryRequest,
        summary: DischargeSummary,
        context: SummaryContext,
    ) -> GenerateSummaryResponse:
        missing_sections = self.collect_missing_fields(summary)
        total_fields = len(summary.__class__.model_fields)
        present_fields = total_fields - len(missing_sections)
        completeness_score = round(present_fields / total_fields, 2)

        result = GenerateSummaryResult(
            discharge_summary=summary,
            prose_version=summary.brief_summary,
            section_metadata=self.build_section_metadata(context),
            completeness_score=completeness_score,
            missing_sections=missing_sections,
        )
        return GenerateSummaryResponse(
            patient_id=request.patient_id,
            result=result,
            errors=[],
        )

    def collect_missing_fields(self, summary: DischargeSummary) -> list[str]:
        payload = summary.model_dump(mode="json")
        missing: list[str] = []
        for field_name, value in payload.items():
            if self._is_missing(value):
                missing.append(field_name)
        return missing

    def build_section_metadata(self, context: SummaryContext) -> list[SectionMetadata]:
        investigations = self._collect_nodes_by_keys(
            context.patient_state,
            self.SECTION_KEYS["investigations"],
        )
        treatment = self._collect_nodes_by_keys(
            context.patient_state,
            self.SECTION_KEYS["treatment"],
        )
        progression = self._collect_nodes_by_keys(
            context.recist_data,
            self.SECTION_KEYS["disease_progression"],
        )
        counselling = context.counselling_facts

        return [
            self._build_metadata("investigations", investigations),
            self._build_metadata("treatment", treatment),
            self._build_metadata("disease_progression", progression),
            self._build_metadata("counselling", counselling),
        ]

    def _build_metadata(self, section: str, nodes: list[Any]) -> SectionMetadata:
        fact_count = len([node for node in nodes if not self._is_empty_node(node)])
        certainty_values = self._extract_certainties(nodes)
        avg_certainty = None
        if certainty_values:
            avg_certainty = round(sum(certainty_values) / len(certainty_values), 2)
        return SectionMetadata(
            section=section,
            fact_count=fact_count,
            avg_certainty=avg_certainty,
        )

    def _collect_nodes_by_keys(
        self,
        payload: Any,
        target_keys: set[str],
    ) -> list[Any]:
        if payload is None:
            return []

        collected: list[Any] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key.lower() in target_keys:
                    collected.extend(self._normalize_node(value))
                collected.extend(self._collect_nodes_by_keys(value, target_keys))
            return collected

        if isinstance(payload, list):
            for item in payload:
                collected.extend(self._collect_nodes_by_keys(item, target_keys))
            return collected

        return []

    def _normalize_node(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        return [value]

    def _extract_certainties(self, payload: Any) -> list[float]:
        values: list[float] = []
        if isinstance(payload, list):
            for item in payload:
                values.extend(self._extract_certainties(item))
            return values

        if isinstance(payload, dict):
            for key, value in payload.items():
                lowered_key = key.lower()
                if lowered_key in {"certainty", "confidence", "score"} and isinstance(
                    value,
                    (float, int),
                ):
                    values.append(self._normalize_certainty(float(value)))
                else:
                    values.extend(self._extract_certainties(value))
        return values

    def _normalize_certainty(self, value: float) -> float:
        if value > 1.0 and value <= 100.0:
            return round(value / 100.0, 4)
        return value

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized in {"", "not available", "n/a", "unknown"}
        if isinstance(value, list):
            return len(value) == 0
        if isinstance(value, dict):
            return all(self._is_missing(item) for item in value.values())
        return False

    def _is_empty_node(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (str, int, float, bool)):
            return False
        if isinstance(value, list):
            return len(value) == 0
        if isinstance(value, dict):
            return len(value) == 0
        return False
