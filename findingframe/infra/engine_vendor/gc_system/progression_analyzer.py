"""
Agent 4: Disease Progression Analyzer

Analyzes GC to determine overall disease status (PD/SD/PR/CR).
Uses the configured project LLM provider.
"""

import os
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from extraction.prompts import (
    NON_TARGET_SUPPLEMENT_PROMPT,
)
from recist import RecistEngine
from recist.recist_engine import check_recist_eligibility
from utils.llm import create_default_llm_client, parse_json_from_text


@dataclass
class ProgressionResult:
    """Result of disease progression analysis."""

    disease_status: str  # PD, SD, PR, or CR
    confidence: float
    key_evidence: list[str]
    timeline_summary: str
    clinical_significance: str
    recommendations: list[str]
    recist_details: dict[str, Any]
    raw_response: str


class ProgressionAnalyzer:
    """
    Analyzes disease progression from longitudinal clinical summaries.
    Uses the configured LLM provider.
    """

    def __init__(self, llm_client: Any | None = None):
        """Initialize the progression analyzer with the configured LLM provider."""
        load_dotenv(dotenv_path="config/.env")
        self.llm_client = llm_client or create_default_llm_client()
        self.recist_engine = RecistEngine()

    def analyze_fact_graph(self, fact_graph: dict[str, Any]) -> ProgressionResult:
        """
        Deterministic progression analysis from the Fact Graph.
        """
        # Phase 5 — RECIST Eligibility Gate
        eligibility = check_recist_eligibility(fact_graph)
        if not eligibility.get("eligible"):
            reason = eligibility.get("reason", "not_applicable")
            return ProgressionResult(
                disease_status=reason,
                confidence=0.0,
                key_evidence=[f"RECIST not applicable: {reason}"],
                timeline_summary="",
                clinical_significance="RECIST criteria do not apply to this patient.",
                recommendations=["Continue standard clinical management."],
                recist_details={"recist_eligibility": eligibility},
                raw_response=json.dumps(eligibility),
            )

        recist = self.recist_engine.evaluate(fact_graph)
        non_target_summary = self._non_target_llm_supplement(fact_graph, recist)
        if non_target_summary.get("non_target_progression") is True:
            recist["non_target_progression"] = True
            if recist.get("recist_classification") not in {"PD"}:
                recist["recist_classification"] = "PD"
        recist["non_target_llm_summary"] = non_target_summary.get("summary", "")
        recist["non_target_llm_confidence"] = non_target_summary.get("confidence", 0.0)
        recist["non_target_llm_used"] = bool(non_target_summary.get("llm_used", False))
        status = recist.get("recist_classification", "Unknown")
        confidence = recist.get("data_completeness_confidence", 0.0)
        evidence = []
        if recist.get("new_lesions"):
            evidence.append("New lesion events detected in timeline.")
        if recist.get("non_target_progression"):
            evidence.append("Non-target lesion progression signal detected.")
        if non_target_summary.get("summary"):
            evidence.append(
                f"Non-target narrative: {non_target_summary.get('summary')}"
            )
        for item in non_target_summary.get("evidence", []):
            evidence.append(str(item))
        evidence.append(
            f"SLD baseline {recist.get('baseline_sld_mm', 0.0)} mm -> current {recist.get('current_sld_mm', 0.0)} mm."
        )
        if recist.get("sld_change_from_nadir_pct") is not None:
            evidence.append(
                f"Change from nadir: {recist.get('sld_change_from_nadir_pct')}%."
            )
        significance = {
            "PD": "Findings meet progression criteria and suggest worsening disease burden.",
            "SD": "Disease burden does not meet progression or response thresholds.",
            "PR": "Tumor burden is reduced consistent with partial response.",
            "CR": "No measurable target lesion burden remains.",
            "Unknown": "Insufficient measurable data for deterministic RECIST classification.",
        }.get(
            status,
            "Insufficient measurable data for deterministic RECIST classification.",
        )

        recommendations = {
            "PD": [
                "Consider treatment escalation or regimen change.",
                "Correlate with non-target lesion findings.",
            ],
            "SD": ["Continue current management and interval imaging follow-up."],
            "PR": ["Continue treatment with routine monitoring for durability."],
            "CR": ["Maintain surveillance protocol and confirm sustained response."],
            "Unknown": [
                "Collect additional measurable lesion data for RECIST assessment."
            ],
        }.get(
            status, ["Collect additional measurable lesion data for RECIST assessment."]
        )

        return ProgressionResult(
            disease_status=status,
            confidence=float(confidence),
            key_evidence=evidence,
            timeline_summary=recist.get("timeline_summary", ""),
            clinical_significance=significance,
            recommendations=recommendations,
            recist_details=recist,
            raw_response=json.dumps(recist),
        )

    def _collect_non_target_events(
        self,
        fact_graph: dict[str, Any],
        recist: dict[str, Any],
    ) -> list[dict[str, Any]]:
        entities = (
            fact_graph.get("entities", {}) if isinstance(fact_graph, dict) else {}
        )
        if not isinstance(entities, dict):
            return []
        target_set = set(recist.get("target_lesions", []) or [])
        payload = []
        for entity_id, entity in entities.items():
            if entity_id in target_set:
                continue
            if not isinstance(entity, dict):
                continue
            events = entity.get("events", [])
            if not isinstance(events, list):
                continue
            for event in sorted(
                events,
                key=lambda item: (
                    str(item.get("date", "")),
                    str(item.get("event_id", "")),
                ),
            ):
                if not isinstance(event, dict):
                    continue
                measurement = event.get("measurement", {})
                payload.append(
                    {
                        "entity_id": entity_id,
                        "date": str(event.get("date", "")),
                        "modality": str(event.get("modality", "OTHER")),
                        "trend": str(event.get("trend", "unknown")),
                        "certainty_label": str(event.get("certainty_label", "unknown")),
                        "certainty": event.get("certainty", 0.0),
                        "measurement_raw": measurement.get("raw_text")
                        if isinstance(measurement, dict)
                        else None,
                    }
                )
        return payload

    def _non_target_llm_supplement(
        self,
        fact_graph: dict[str, Any],
        recist: dict[str, Any],
    ) -> dict[str, Any]:
        events = self._collect_non_target_events(fact_graph, recist)
        if not events:
            return {
                "non_target_progression": False,
                "summary": "",
                "evidence": [],
                "confidence": 0.0,
                "llm_used": False,
            }
        prompt = NON_TARGET_SUPPLEMENT_PROMPT.format(
            non_target_events_json=json.dumps(events, indent=2),
        )
        try:
            response = self._call_llm(prompt)
            parsed = parse_json_from_text(response)
            if not isinstance(parsed, dict):
                raise ValueError("non-target supplement not an object")
            return {
                "non_target_progression": bool(
                    parsed.get("non_target_progression", False)
                ),
                "summary": str(parsed.get("summary", "")).strip(),
                "evidence": parsed.get("evidence", [])
                if isinstance(parsed.get("evidence", []), list)
                else [],
                "confidence": float(parsed.get("confidence", 0.0) or 0.0),
                "llm_used": True,
            }
        except Exception:
            # Deterministic fallback if LLM fails.
            has_progressive_signal = any(
                str(item.get("trend", "")).lower() in {"increasing", "new"}
                for item in events
            )
            return {
                "non_target_progression": has_progressive_signal,
                "summary": "Fallback non-target interpretation based on event trend signals.",
                "evidence": [
                    f"{item.get('entity_id')}: {item.get('trend')}"
                    for item in events
                    if str(item.get("trend", "")).lower() in {"increasing", "new"}
                ],
                "confidence": 0.5 if has_progressive_signal else 0.35,
                "llm_used": False,
            }

    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM provider with the given prompt."""
        return self.llm_client.chat(prompt, max_tokens=4000)
