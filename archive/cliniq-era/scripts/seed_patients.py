#!/usr/bin/env python3
"""Seed the fact-graph-service with patient data from TMC outputs and gold annotations."""

import json
import sys
from pathlib import Path

import httpx

FACT_GRAPH_URL = "http://localhost:5006"

# Patient metadata
PATIENTS = {
    "10000935": {"cancer_type": "Gastric", "source": "fact_graph"},
    "19540374": {"cancer_type": "Lung", "source": "gold"},
    "10016197": {"cancer_type": "Colon", "source": "gold"},
    "11392257": {"cancer_type": "Breast", "source": "gold"},
    "10511269": {"cancer_type": "Brain", "source": "gold"},
}

TMC_ROOT = Path(__file__).parent.parent / "tmc"
OUTPUTS = TMC_ROOT / "outputs"
GOLD_DIR = TMC_ROOT / "evaluation" / "manual_annotations"

# Certainty label -> numeric score mapping (matches FactStore convention)
CERTAINTY_SCORES = {
    "confirmed": 0.96,
    "suspected": 0.80,
    "differential": 0.60,
    "uncertain": 0.35,
    "negative": 0.99,
}


def load_fact_graph(patient_id: str) -> dict | None:
    """Try to load an existing fact graph JSON for this patient."""
    candidates = [
        OUTPUTS / "eval_v14_paired" / f"subject_{patient_id}_fact_graph.json",
        OUTPUTS / "patient_gcs" / f"subject_{patient_id}_fact_graph.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return None


def gold_to_fact_graph(patient_id: str) -> dict:
    """Generate a fact graph from gold annotations.

    Gold files have ``gold_entities`` as a flat list.  Each entry carries
    ``entity_id``, ``canonical_name``, ``source_report``, ``certainty``
    (label string), ``is_negated``, ``body_region``, ``radlex_id``, and
    ``evidence_text`` among other optional keys.
    """
    gold_path = GOLD_DIR / f"gold_{patient_id}.json"
    if not gold_path.exists():
        print(f"  WARNING: No gold file for {patient_id}")
        return {"schema_version": 2, "subject_id": patient_id, "entities": {}, "metadata": {}}

    with open(gold_path) as f:
        gold = json.load(f)

    # Group gold entities by entity_id so multiple reports roll up into one
    # EntityNode with multiple events.
    grouped: dict[str, list[dict]] = {}
    for ent in gold.get("gold_entities", []):
        eid = ent.get("entity_id", "unknown")
        grouped.setdefault(eid, []).append(ent)

    entities: dict[str, dict] = {}
    for entity_id, occurrences in grouped.items():
        # Use the first occurrence for stable entity-level metadata
        first = occurrences[0]
        canonical_name = first.get("canonical_name", entity_id)
        radlex_id = first.get("radlex_id")
        snomed_id = first.get("snomed_id")
        body_region = first.get("body_region")
        entity_type = first.get("entity_type", "finding")

        events = []
        for idx, occ in enumerate(occurrences):
            report_num = occ.get("source_report", 1)
            cert_label = occ.get("certainty", "suspected")
            cert_score = CERTAINTY_SCORES.get(cert_label, 0.5)
            date = occ.get("date", "2025-01-01")

            event = {
                "event_id": f"evt_{patient_id}_{entity_id}_r{report_num}_{idx:03d}",
                "entity_id": entity_id,
                "date": date,
                "source_report_id": f"report_{report_num}",
                "hadm_id": "",
                "modality": occ.get("modality", "CT"),
                "measurement": {
                    "value": None,
                    "unit": None,
                    "normalized_mm": None,
                    "is_qualitative": True,
                    "raw_text": None,
                    "delta_mm": None,
                },
                "certainty": cert_score,
                "certainty_label": cert_label,
                "comparison_to_prior": None,
                "trend": "unknown",
                "is_negated": occ.get("is_negated", False),
                "source": "gold",
                "confidence": cert_score,
            }
            events.append(event)

        dates_sorted = sorted(e["date"] for e in events)
        entities[entity_id] = {
            "entity_id": entity_id,
            "canonical_name": canonical_name,
            "radlex_id": radlex_id,
            "snomed_id": snomed_id,
            "entity_type": entity_type,
            "anatomical_site": first.get("anatomical_site", ""),
            "first_documented": dates_sorted[0],
            "last_documented": dates_sorted[-1],
            "events": events,
            "certainty_trajectory": [
                {
                    "date": e["date"],
                    "certainty": e["certainty"],
                    "certainty_label": e["certainty_label"],
                }
                for e in events
            ],
            "status": "active",
            "body_region": body_region,
        }

    return {
        "schema_version": 2,
        "subject_id": patient_id,
        "entities": entities,
        "metadata": {"source": "gold_annotations"},
    }


def seed_patient(patient_id: str, info: dict):
    print(f"Seeding patient {patient_id} ({info['cancer_type']})...")

    # Try loading existing fact graph first
    fg = load_fact_graph(patient_id)
    if fg:
        print(f"  Found existing fact graph ({len(fg.get('entities', {}))} entities)")
    else:
        print(f"  No fact graph found, generating from gold annotations...")
        fg = gold_to_fact_graph(patient_id)
        print(f"  Generated ({len(fg.get('entities', {}))} entities)")

    # POST to fact-graph-service
    try:
        resp = httpx.post(
            f"{FACT_GRAPH_URL}/api/v1/patient/{patient_id}/import",
            json={"patient_id": patient_id, "fact_graph": fg},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Imported: {result}")
    except Exception as e:
        print(f"  ERROR: {e}")


def main():
    global FACT_GRAPH_URL
    url = sys.argv[1] if len(sys.argv) > 1 else FACT_GRAPH_URL
    FACT_GRAPH_URL = url

    for pid, info in PATIENTS.items():
        seed_patient(pid, info)

    # Verify
    try:
        resp = httpx.get(f"{FACT_GRAPH_URL}/api/v1/patients", timeout=10)
        patients = resp.json()
        print(f"\nSeeded {len(patients)} patients:")
        for p in patients:
            print(f"  {p['patient_id']}: {p['entity_count']} entities, {p['event_count']} events")
    except Exception as e:
        print(f"Verification failed: {e}")


if __name__ == "__main__":
    main()
