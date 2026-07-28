"""
Deterministic RECIST 1.1 engine for target-lesion SLD tracking.
"""

from __future__ import annotations

from typing import Any

from .lesion_selector import select_target_lesions


# Entity types and canonical names that signal oncologic context.
_ONCOLOGY_SIGNALS = {
    "metastasis", "metastatic", "neoplasm", "tumor", "malignant",
    "carcinoma", "lymphoma", "sarcoma", "adenocarcinoma", "melanoma",
    "primary", "primary_lung", "primary_breast", "neoplastic",
}

# Entity types to exclude from RECIST eligibility.
_NON_ONCOLOGIC_TYPES = {
    "degenerative", "fracture", "effusion", "cyst", "impression_summary",
    "negative_finding",
}


def check_recist_eligibility(fact_graph: dict[str, Any]) -> dict[str, Any]:
    """
    Check whether a patient's fact graph is eligible for RECIST 1.1 assessment.

    Returns:
        dict with:
          - eligible: bool
          - reason: str   ('eligible' | 'not_applicable' | 'non_measurable')
          - has_oncologic_context: bool
          - measurable_count: int
    """
    entities = fact_graph.get("entities", {}) if isinstance(fact_graph, dict) else {}
    if not isinstance(entities, dict):
        entities = {}

    has_oncologic_context = False
    measurable_count = 0

    for entity_id, entity in entities.items():
        if not isinstance(entity, dict):
            continue

        etype = str(entity.get("entity_type", "")).lower()
        name_lower = str(entity.get("canonical_name", entity_id)).lower()

        # Check for oncologic context
        if etype in _ONCOLOGY_SIGNALS or any(sig in name_lower for sig in _ONCOLOGY_SIGNALS):
            has_oncologic_context = True

        # Skip non-oncologic entities for measurability check
        if etype in _NON_ONCOLOGIC_TYPES:
            continue

        # Check for measurable events (≥10mm)
        events = entity.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            measurement = event.get("measurement", {})
            if not isinstance(measurement, dict):
                continue
            mm = measurement.get("normalized_mm")
            if mm is not None:
                try:
                    if float(mm) >= 10.0:
                        measurable_count += 1
                        break  # one per entity is enough
                except (ValueError, TypeError):
                    pass

    if not has_oncologic_context:
        return {
            "eligible": False,
            "reason": "not_applicable",
            "has_oncologic_context": False,
            "measurable_count": measurable_count,
        }

    if measurable_count == 0:
        return {
            "eligible": False,
            "reason": "non_measurable",
            "has_oncologic_context": True,
            "measurable_count": 0,
        }

    return {
        "eligible": True,
        "reason": "eligible",
        "has_oncologic_context": True,
        "measurable_count": measurable_count,
    }


class RecistEngine:
    def __init__(
        self,
        max_target_lesions: int = 5,
        max_target_per_organ: int = 2,
        measurable_threshold_mm: float = 10.0,
    ):
        self.max_target_lesions = max_target_lesions
        self.max_target_per_organ = max_target_per_organ
        self.measurable_threshold_mm = measurable_threshold_mm

    def evaluate(self, fact_graph: dict[str, Any]) -> dict[str, Any]:
        entities = fact_graph.get("entities", {}) if isinstance(fact_graph, dict) else {}
        if not isinstance(entities, dict):
            entities = {}

        target_lesions = select_target_lesions(
            fact_graph,
            max_total=self.max_target_lesions,
            max_per_organ=self.max_target_per_organ,
            measurable_threshold_mm=self.measurable_threshold_mm,
        )
        non_target_lesions = [entity_id for entity_id in entities.keys() if entity_id not in target_lesions]

        new_lesions = self._detect_new_lesions(entities)
        non_target_progression = self._detect_non_target_progression(entities, non_target_lesions)
        sld_by_date = self._compute_sld_by_date(entities, target_lesions)

        timeline_dates = sorted(sld_by_date.keys())
        baseline_sld = sld_by_date[timeline_dates[0]] if timeline_dates else 0.0
        current_sld = sld_by_date[timeline_dates[-1]] if timeline_dates else 0.0
        nadir_sld = min(sld_by_date.values()) if sld_by_date else 0.0

        change_baseline_pct = None
        if baseline_sld > 0:
            change_baseline_pct = round(((current_sld - baseline_sld) / baseline_sld) * 100.0, 2)
        change_nadir_pct = None
        if nadir_sld > 0:
            change_nadir_pct = round(((current_sld - nadir_sld) / nadir_sld) * 100.0, 2)

        classification = self._classify(
            baseline_sld=baseline_sld,
            nadir_sld=nadir_sld,
            current_sld=current_sld,
            change_baseline_pct=change_baseline_pct,
            change_nadir_pct=change_nadir_pct,
            new_lesions=new_lesions,
            non_target_progression=non_target_progression,
            has_target=bool(target_lesions),
        )

        confidence = self._confidence(
            target_count=len(target_lesions),
            timeline_count=len(timeline_dates),
            has_new_signal=new_lesions or non_target_progression,
            has_measurement=bool(sld_by_date),
        )

        timeline_summary = self._timeline_summary(sld_by_date)
        return {
            "target_lesions": target_lesions,
            "non_target_lesions": non_target_lesions,
            "baseline_sld_mm": baseline_sld,
            "nadir_sld_mm": nadir_sld,
            "current_sld_mm": current_sld,
            "sld_change_from_baseline_pct": change_baseline_pct,
            "sld_change_from_nadir_pct": change_nadir_pct,
            "new_lesions": new_lesions,
            "non_target_progression": non_target_progression,
            "recist_classification": classification,
            "sld_by_date": sld_by_date,
            "timeline_summary": timeline_summary,
            "data_completeness_confidence": confidence,
        }

    def _entity_measurements(self, entity: dict[str, Any]) -> dict[str, float]:
        events = entity.get("events", [])
        if not isinstance(events, list):
            return {}
        values: dict[str, float] = {}
        for event in sorted(events, key=lambda item: str(item.get("date", ""))):
            if not isinstance(event, dict):
                continue
            date = str(event.get("date", ""))
            if not date:
                continue
            measurement = event.get("measurement", {})
            if not isinstance(measurement, dict):
                continue
            if bool(measurement.get("is_qualitative", False)):
                continue
            mm = measurement.get("normalized_mm")
            if mm is None:
                continue
            try:
                values[date] = float(mm)
            except Exception:
                continue
        return values

    def _compute_sld_by_date(self, entities: dict[str, Any], target_lesions: list[str]) -> dict[str, float]:
        if not target_lesions:
            return {}
        all_dates: set[str] = set()
        per_target = {}
        for target in target_lesions:
            entity = entities.get(target, {})
            measurements = self._entity_measurements(entity if isinstance(entity, dict) else {})
            per_target[target] = measurements
            all_dates.update(measurements.keys())

        dates = sorted(all_dates)
        sld_by_date: dict[str, float] = {}
        last_seen_per_target: dict[str, float] = {}
        for date in dates:
            total = 0.0
            have_any = False
            for target in target_lesions:
                measurements = per_target.get(target, {})
                if date in measurements:
                    last_seen_per_target[target] = measurements[date]
                if target in last_seen_per_target:
                    total += last_seen_per_target[target]
                    have_any = True
            if have_any:
                sld_by_date[date] = round(total, 2)
        return sld_by_date

    def _detect_new_lesions(self, entities: dict[str, Any]) -> bool:
        if not entities:
            return False
        all_dates = []
        first_by_entity = {}
        for entity_id, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            events = entity.get("events", [])
            if not isinstance(events, list) or not events:
                continue
            dates = sorted([str(e.get("date", "")) for e in events if isinstance(e, dict) and str(e.get("date", ""))])
            if not dates:
                continue
            first_by_entity[entity_id] = dates[0]
            all_dates.extend(dates)
            if any(str(e.get("trend", "")).lower() == "new" for e in events if isinstance(e, dict)):
                return True
        if not all_dates:
            return False
        baseline = min(all_dates)
        return any(first_date > baseline for first_date in first_by_entity.values())

    def _detect_non_target_progression(self, entities: dict[str, Any], non_target_lesions: list[str]) -> bool:
        for entity_id in non_target_lesions:
            entity = entities.get(entity_id, {})
            if not isinstance(entity, dict):
                continue
            events = entity.get("events", [])
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                trend = str(event.get("trend", "")).lower()
                if trend in {"increasing", "new"}:
                    return True
        return False

    def _classify(
        self,
        baseline_sld: float,
        nadir_sld: float,
        current_sld: float,
        change_baseline_pct: float | None,
        change_nadir_pct: float | None,
        new_lesions: bool,
        non_target_progression: bool,
        has_target: bool,
    ) -> str:
        if new_lesions or non_target_progression:
            return "PD"
        if not has_target:
            return "Unknown"
        if current_sld == 0.0:
            return "CR"
        if change_nadir_pct is not None and change_nadir_pct >= 20.0 and (current_sld - nadir_sld) >= 5.0:
            return "PD"
        if change_baseline_pct is not None and change_baseline_pct <= -30.0:
            return "PR"
        return "SD"

    def _confidence(
        self,
        target_count: int,
        timeline_count: int,
        has_new_signal: bool,
        has_measurement: bool,
    ) -> float:
        confidence = 0.0
        if has_measurement:
            confidence += 0.35
        confidence += min(target_count / 5.0, 1.0) * 0.35
        confidence += min(timeline_count / 4.0, 1.0) * 0.2
        if has_new_signal:
            confidence += 0.1
        return round(min(confidence, 1.0), 2)

    def _timeline_summary(self, sld_by_date: dict[str, float]) -> str:
        if not sld_by_date:
            return "No measurable target lesion timeline available."
        points = ", ".join([f"{date}: {mm} mm" for date, mm in sorted(sld_by_date.items())])
        return f"SLD trajectory across {len(sld_by_date)} timepoints -> {points}."
