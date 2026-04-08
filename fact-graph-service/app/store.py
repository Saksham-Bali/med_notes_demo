"""
PatientStore — CFS ClinicalFact → FactStore adapter.

One FactStore instance per patient, stored in data/{patient_id}/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fact_graph.fact_store import FactStore
from .models import ClinicalFact, MeasurementInput


def _measurement_to_finding_dict(m: MeasurementInput | None) -> dict[str, Any]:
    """Convert a CFS MeasurementInput into the nested measurement dict that
    FactStore._measurement_from_finding() understands."""
    if m is None:
        return {}
    # FactStore checks finding["measurement_normalized"] first; use it if we
    # have a normalized_mm value so it is preserved faithfully.
    if m.normalized_mm is not None:
        return {
            "measurement_normalized": {
                "value": m.value,
                "unit": m.unit,
                "value_mm": m.normalized_mm,
                "raw_text": m.raw_text,
                "is_qualitative": False,
                "delta_mm": None,
            }
        }
    # Otherwise fall back to the simple {"current": raw_text} form.
    return {
        "measurement": {
            "current": m.raw_text or "",
            "trend": "",
        }
    }


def _fact_to_finding(fact: ClinicalFact) -> dict[str, Any]:
    """Map a ClinicalFact to the `finding` dict expected by append_grounded_finding."""
    finding: dict[str, Any] = {
        # certainty_label is read from finding["certainty"]
        "certainty": fact.certainty_label,
        "confidence_score": fact.certainty,
        "is_negated": fact.is_negated,
        "negation_language": None,
        "anatomical_location": fact.body_region or "",
        "finding_type": "finding",
        "temporal_qualifier": fact.temporal_change or "",
        "comparison_to_prior": fact.temporal_change or "",
        # evidence_surface is stored via evidence_text key
        "evidence_text": fact.evidence_text or "",
        "source": "llm",
        "span_start": -1,
        "span_end": -1,
    }
    # Merge measurement fields at the top level of the finding dict.
    finding.update(_measurement_to_finding_dict(fact.measurement))
    return finding


def _fact_to_grounded_entity(fact: ClinicalFact) -> dict[str, Any]:
    """Map a ClinicalFact to the `grounded_entity` dict expected by append_grounded_finding."""
    return {
        "canonical_name": fact.entity_name,
        "radlex_id": fact.radlex_id,
        "radlex_label": None,
        "snomed_id": fact.snomed_id,
        "grounding_method": "cfs_direct",
        "grounding_confidence": fact.certainty,
    }


class PatientStore:
    """One FactStore instance per patient, stored in data/{patient_id}/."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._stores: dict[str, FactStore] = {}

    def _get(self, patient_id: str) -> FactStore:
        if patient_id not in self._stores:
            patient_dir = self.data_dir / patient_id
            patient_dir.mkdir(parents=True, exist_ok=True)
            store = FactStore(
                subject_id=patient_id,
                output_dir=str(patient_dir),
            )
            store.load()
            self._stores[patient_id] = store
        return self._stores[patient_id]

    def ingest(self, facts: list[ClinicalFact]) -> dict[str, Any]:
        """Ingest a list of ClinicalFacts (may span multiple patients).

        Returns aggregated stats: facts_ingested, entities_created, entities_updated.
        """
        # Group facts by patient_id.
        by_patient: dict[str, list[ClinicalFact]] = {}
        for fact in facts:
            by_patient.setdefault(fact.patient_id, []).append(fact)

        total_facts_ingested = 0
        total_entities_created = 0
        total_entities_updated = 0

        for patient_id, patient_facts in by_patient.items():
            store = self._get(patient_id)
            before_entity_ids = set(store.graph.entities.keys())

            for idx, fact in enumerate(patient_facts):
                finding = _fact_to_finding(fact)
                grounded_entity = _fact_to_grounded_entity(fact)
                store.append_grounded_finding(
                    finding=finding,
                    grounded_entity=grounded_entity,
                    report_date=fact.date,
                    hadm_id=fact.hadm_id or "",
                    report_id=fact.source_report_id or fact.fact_id,
                    modality=fact.modality or "unknown",
                    event_index=idx,
                )
                total_facts_ingested += 1

            after_entity_ids = set(store.graph.entities.keys())
            new_ids = after_entity_ids - before_entity_ids
            total_entities_created += len(new_ids)
            total_entities_updated += len(after_entity_ids - new_ids)

            store.save()

        return {
            "facts_ingested": total_facts_ingested,
            "entities_created": total_entities_created,
            "entities_updated": total_entities_updated,
        }

    def get_state(self, patient_id: str) -> dict[str, Any]:
        """Return the current entity state for a patient as a serialisable dict."""
        store = self._get(patient_id)
        graph = store.get_patient_graph()
        entities_out: list[dict[str, Any]] = []
        for entity in graph.entities.values():
            entities_out.append({
                "entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "radlex_id": entity.radlex_id,
                "snomed_id": entity.snomed_id,
                "entity_type": entity.entity_type,
                "anatomical_site": entity.anatomical_site,
                "body_region": entity.body_region,
                "first_documented": entity.first_documented,
                "last_documented": entity.last_documented,
                "status": entity.status,
                "event_count": len(entity.events),
                "certainty_trajectory": [
                    p.model_dump() for p in entity.certainty_trajectory
                ],
            })
        return {
            "patient_id": patient_id,
            "schema_version": graph.schema_version,
            "entity_count": len(entities_out),
            "entities": entities_out,
        }

    def get_timeline(self, patient_id: str) -> dict[str, Any]:
        """Return all events for a patient sorted chronologically."""
        store = self._get(patient_id)
        graph = store.get_patient_graph()

        events_out: list[dict[str, Any]] = []
        for entity in graph.entities.values():
            for event in entity.events:
                events_out.append({
                    "event_id": event.event_id,
                    "entity_id": event.entity_id,
                    "canonical_name": entity.canonical_name,
                    "date": event.date,
                    "source_report_id": event.source_report_id,
                    "hadm_id": event.hadm_id,
                    "modality": event.modality,
                    "certainty": event.certainty,
                    "certainty_label": event.certainty_label,
                    "trend": event.trend,
                    "is_negated": event.is_negated,
                    "measurement": event.measurement.model_dump(),
                })

        events_out.sort(key=lambda e: (e["date"], e["event_id"]))

        return {
            "patient_id": patient_id,
            "event_count": len(events_out),
            "events": events_out,
        }

    def get_entity_history(self, patient_id: str, entity_id: str) -> dict[str, Any]:
        """Return the full event history for a single entity."""
        store = self._get(patient_id)
        entity = store.get_entity(entity_id)
        if entity is None:
            return {}
        events_out = []
        for event in entity.events:
            events_out.append({
                "event_id": event.event_id,
                "date": event.date,
                "source_report_id": event.source_report_id,
                "hadm_id": event.hadm_id,
                "modality": event.modality,
                "certainty": event.certainty,
                "certainty_label": event.certainty_label,
                "trend": event.trend,
                "is_negated": event.is_negated,
                "negation_language": event.negation_language,
                "uncertainty_language": event.uncertainty_language,
                "comparison_to_prior": event.comparison_to_prior,
                "measurement": event.measurement.model_dump(),
                "span_start": event.span_start,
                "span_end": event.span_end,
                "source": event.source,
                "confidence": event.confidence,
            })
        return {
            "patient_id": patient_id,
            "entity_id": entity.entity_id,
            "canonical_name": entity.canonical_name,
            "radlex_id": entity.radlex_id,
            "snomed_id": entity.snomed_id,
            "status": entity.status,
            "first_documented": entity.first_documented,
            "last_documented": entity.last_documented,
            "body_region": entity.body_region,
            "event_count": len(events_out),
            "events": events_out,
            "certainty_trajectory": [p.model_dump() for p in entity.certainty_trajectory],
        }

    def import_graph(self, patient_id: str, raw_graph: dict) -> dict:
        """Import a raw TMC fact graph JSON.

        Writes the JSON file in the exact format/location that FactStore.load()
        expects (``subject_{patient_id}_fact_graph.json`` inside the patient dir)
        and forces a reload so subsequent queries work.
        """
        import json

        patient_dir = self.data_dir / patient_id
        patient_dir.mkdir(parents=True, exist_ok=True)

        # FactStore expects subject_{id}_fact_graph.json
        fg_path = patient_dir / f"subject_{patient_id}_fact_graph.json"
        with open(fg_path, "w") as f:
            json.dump(raw_graph, f, indent=2)

        # Force reload so the in-memory cache picks up the new file
        if patient_id in self._stores:
            del self._stores[patient_id]

        # Trigger a load to validate and back-fill into SQLite
        self._get(patient_id)

        entities = raw_graph.get("entities", {})
        return {
            "patient_id": patient_id,
            "entities_loaded": len(entities),
            "status": "imported",
        }

    def list_patients(self) -> list[dict]:
        """List all patients with summary stats."""
        patients: list[dict] = []
        if not self.data_dir.exists():
            return patients
        for patient_dir in sorted(self.data_dir.iterdir()):
            if not patient_dir.is_dir():
                continue
            patient_id = patient_dir.name
            try:
                store = self._get(patient_id)
                graph = store.get_patient_graph()
                event_count = 0
                body_regions: set[str] = set()
                all_dates: list[str] = []
                for entity in graph.entities.values():
                    event_count += len(entity.events)
                    if entity.body_region:
                        body_regions.add(entity.body_region)
                    for ev in entity.events:
                        if ev.date:
                            all_dates.append(ev.date)
                all_dates.sort()
                patients.append({
                    "patient_id": patient_id,
                    "entity_count": len(graph.entities),
                    "event_count": event_count,
                    "first_event_date": all_dates[0] if all_dates else None,
                    "last_event_date": all_dates[-1] if all_dates else None,
                    "body_regions": sorted(body_regions),
                })
            except Exception:
                patients.append({
                    "patient_id": patient_id,
                    "entity_count": 0,
                    "event_count": 0,
                    "first_event_date": None,
                    "last_event_date": None,
                    "body_regions": [],
                })
        return patients

    def check_conflicts(self, patient_id: str, facts: list[ClinicalFact]) -> dict[str, Any]:
        """Check incoming facts against the existing graph for conflicts.

        A conflict is raised when a fact contradicts the current entity status
        (e.g., a new confirmed finding for an entity marked 'resolved').
        """
        store = self._get(patient_id)
        conflicts: list[dict[str, Any]] = []

        for fact in facts:
            entity = store.get_entity(fact.entity_name)
            if entity is None:
                continue
            conflict_reasons: list[str] = []
            # Conflict: entity is resolved but new fact is confirmed present
            if entity.status == "resolved" and not fact.is_negated and fact.certainty_label in {"confirmed", "suspected"}:
                conflict_reasons.append(
                    f"Entity '{fact.entity_name}' is currently 'resolved' but new fact asserts presence "
                    f"with certainty_label='{fact.certainty_label}'."
                )
            # Conflict: entity is absent but new fact is confirmed present
            if entity.status == "absent" and not fact.is_negated:
                conflict_reasons.append(
                    f"Entity '{fact.entity_name}' is currently 'absent' but new fact asserts presence."
                )
            # Conflict: entity is active/confirmed but new fact is a strong negation
            if entity.status == "active" and fact.is_negated:
                conflict_reasons.append(
                    f"Entity '{fact.entity_name}' is currently 'active' but new fact negates it."
                )
            if conflict_reasons:
                conflicts.append({
                    "entity_name": fact.entity_name,
                    "current_status": entity.status,
                    "new_fact_certainty_label": fact.certainty_label,
                    "new_fact_is_negated": fact.is_negated,
                    "reasons": conflict_reasons,
                })

        return {
            "patient_id": patient_id,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
        }
