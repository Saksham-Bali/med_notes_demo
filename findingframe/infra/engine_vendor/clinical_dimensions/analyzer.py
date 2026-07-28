"""
Clinical dimensions analyzer for Fact Graph entities.

Implements:
1) Uncertainty trajectory classification + transition events
2) Modality coverage / absence detection
3) Cross-modality certainty boosting
"""

from __future__ import annotations

import copy
from typing import Any


class ClinicalDimensionAnalyzer:
    def __init__(self, certainty_boost_factor: float = 1.1):
        self.certainty_boost_factor = certainty_boost_factor
        self._certainty_rank = {
            "uncertain": 0,
            "differential": 1,
            "suspected": 2,
            "confirmed": 3,
            "negative": 3,
        }

    def analyze(self, fact_graph: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Analyze a fact graph and return:
        - updated_fact_graph: with cross-modality certainty boosts applied
        - dimensions: derived clinical dimensions metadata
        """
        graph = copy.deepcopy(fact_graph or {})
        entities = graph.get("entities", {})
        if not isinstance(entities, dict):
            entities = {}
            graph["entities"] = entities

        certainty_summary: dict[str, Any] = {}
        modality_summary: dict[str, Any] = {}
        transition_events: list[dict[str, Any]] = []

        initially_uncertain = 0
        resolved_to_confirmed = 0

        for entity_id, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            events = entity.get("events", [])
            if not isinstance(events, list):
                events = []
                entity["events"] = events
            events = sorted(
                [e for e in events if isinstance(e, dict)],
                key=lambda item: (str(item.get("date", "")), str(item.get("event_id", ""))),
            )
            entity["events"] = events

            trajectory_points = self._trajectory_points(entity, events)
            labels = [p["certainty_label"] for p in trajectory_points]
            trajectory_class = self._classify_trajectory(labels)
            certainty_summary[entity_id] = {
                "trajectory_class": trajectory_class,
                "points": trajectory_points,
            }

            if labels:
                if self._certainty_rank.get(labels[0], 0) < self._certainty_rank["confirmed"]:
                    initially_uncertain += 1
                    if any(self._certainty_rank.get(label, 0) >= self._certainty_rank["confirmed"] for label in labels[1:]):
                        resolved_to_confirmed += 1

            transitions = self._detect_transitions(entity_id, trajectory_points)
            transition_events.extend(transitions)

            modality = self._modality_coverage(events)
            modality_summary[entity_id] = modality
            if modality["cross_modality_confirmed"]:
                self._apply_cross_modality_boost(events)

        resolution_rate = (
            round((resolved_to_confirmed / initially_uncertain) * 100.0, 2)
            if initially_uncertain > 0
            else 0.0
        )

        dimensions = {
            "certainty_trajectories": certainty_summary,
            "transition_events": transition_events,
            "certainty_resolution_rate_percent": resolution_rate,
            "modality_coverage": modality_summary,
        }
        return graph, dimensions

    def _trajectory_points(self, entity: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points = entity.get("certainty_trajectory", [])
        parsed = []
        if isinstance(points, list) and points:
            for point in points:
                if not isinstance(point, dict):
                    continue
                date = str(point.get("date", ""))
                label = str(point.get("certainty_label", point.get("certainty_level", "unknown"))).lower()
                certainty = point.get("certainty", self._certainty_to_score(label))
                parsed.append(
                    {
                        "date": date,
                        "certainty_label": label,
                        "certainty": float(certainty if certainty is not None else self._certainty_to_score(label)),
                    }
                )
        if parsed:
            return sorted(parsed, key=lambda item: item["date"])

        # Fallback from events when trajectory array is absent.
        for event in events:
            label = str(event.get("certainty_label", "unknown")).lower()
            parsed.append(
                {
                    "date": str(event.get("date", "")),
                    "certainty_label": label,
                    "certainty": float(event.get("certainty", self._certainty_to_score(label))),
                }
            )
        # Deduplicate same date/label pairs.
        seen = set()
        deduped = []
        for p in sorted(parsed, key=lambda item: item["date"]):
            key = (p["date"], p["certainty_label"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)
        return deduped

    def _certainty_to_score(self, label: str) -> float:
        rank = self._certainty_rank.get((label or "").lower(), 1)
        if rank <= 0:
            return 0.35
        if rank == 1:
            return 0.6
        if rank == 2:
            return 0.8
        return 0.95

    def _classify_trajectory(self, labels: list[str]) -> str:
        if not labels:
            return "stable-suspected"
        levels = [self._certainty_rank.get(label, 1) for label in labels]
        first = levels[0]
        last = levels[-1]
        if last > first:
            return "escalating"
        if last < first:
            return "declining"
        if all(level >= self._certainty_rank["confirmed"] for level in levels):
            return "stable-confirmed"
        return "stable-suspected"

    def _detect_transitions(self, entity_id: str, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        transitions: list[dict[str, Any]] = []
        for idx in range(1, len(points)):
            prev = points[idx - 1]
            curr = points[idx]
            prev_rank = self._certainty_rank.get(prev["certainty_label"], 1)
            curr_rank = self._certainty_rank.get(curr["certainty_label"], 1)
            if prev_rank < self._certainty_rank["confirmed"] and curr_rank >= self._certainty_rank["confirmed"]:
                transitions.append(
                    {
                        "entity_id": entity_id,
                        "date": curr["date"],
                        "transition_type": "certainty_escalation_to_confirmed",
                        "from_label": prev["certainty_label"],
                        "to_label": curr["certainty_label"],
                    }
                )
            elif prev_rank >= self._certainty_rank["confirmed"] and curr_rank < self._certainty_rank["confirmed"]:
                transitions.append(
                    {
                        "entity_id": entity_id,
                        "date": curr["date"],
                        "transition_type": "certainty_decline_from_confirmed",
                        "from_label": prev["certainty_label"],
                        "to_label": curr["certainty_label"],
                    }
                )
        return transitions

    def _modality_coverage(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        detected_modalities = set()
        absence_events: list[dict[str, Any]] = []
        confirmed_modalities = set()

        for event in events:
            modality = str(event.get("modality", "OTHER")).upper()
            detected_modalities.add(modality)
            label = str(event.get("certainty_label", "")).lower()
            certainty = float(event.get("certainty", 0.0) or 0.0)
            if label == "confirmed" or certainty >= 0.9:
                confirmed_modalities.add(modality)

            if self._has_absence_signal(event):
                absence_events.append(
                    {
                        "date": str(event.get("date", "")),
                        "modality": modality,
                        "signal": "not_seen_or_negative_reported",
                    }
                )

        return {
            "detected_modalities": sorted(detected_modalities),
            "absence_events": absence_events,
            "cross_modality_confirmed": len(confirmed_modalities) >= 2,
        }

    def _has_absence_signal(self, event: dict[str, Any]) -> bool:
        measurement = event.get("measurement", {})
        raw_text = ""
        if isinstance(measurement, dict):
            raw_text = str(measurement.get("raw_text", "")).lower()
        extra = " ".join(
            [
                str(event.get("uncertainty_language", "")),
                str(event.get("comparison_to_prior", "")),
                str(event.get("trend", "")),
            ]
        ).lower()
        text = f"{raw_text} {extra}"
        needles = [
            "not seen",
            "not visualized",
            "no evidence",
            "absent",
            "resolved",
        ]
        return any(needle in text for needle in needles)

    def _apply_cross_modality_boost(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            label = str(event.get("certainty_label", "")).lower()
            certainty = float(event.get("certainty", 0.0) or 0.0)
            if label != "confirmed" and certainty < 0.9:
                continue
            boosted = min(1.0, round(certainty * self.certainty_boost_factor, 3))
            event["certainty"] = boosted
