"""
Deterministic cross-track relationship graph for FindingFrame tracks.

Produces a lightweight ``TrackGraph``: a dict mapping track_key -> list of
TrackRelationship objects.  All relationships are computed deterministically
from frame timelines, anatomy taxonomy, and shared evidence spans.  No LLM.

Version 2 includes four observed edge types:
  - FINDING_PROGRESSION     (same-track temporal chain, replaces v1 TEMPORAL_COOCCURRENCE)
  - STATUS_COEVOLUTION      (cross-track co-progression: co_worsening / co_improving / co_stable)
  - ANATOMICAL_RELATIONSHIP (3-tier organ-level proximity, replaces v1 coarse grouping)
  - EVIDENCE_PROXIMITY      (evidence-span proximity + assertion polarity, replaces v1 EXPLICIT)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Edge type constants
# ---------------------------------------------------------------------------
FINDING_PROGRESSION = "FINDING_PROGRESSION"
STATUS_COEVOLUTION = "STATUS_COEVOLUTION"
ANATOMICAL_RELATIONSHIP = "ANATOMICAL_RELATIONSHIP"
EVIDENCE_PROXIMITY = "EVIDENCE_PROXIMITY"

# Legacy aliases for backward-compatible callers.
TEMPORAL_COOCCURRENCE = FINDING_PROGRESSION
ANATOMICAL_PROXIMITY = ANATOMICAL_RELATIONSHIP
EXPLICIT_COOCCURRENCE = EVIDENCE_PROXIMITY

# Edge classes.
OBSERVED = "observed"
INFERRED = "inferred"
ADJUDICATED = "adjudicated"

# Review statuses.
UNREVIEWED = "unreviewed"
ENGINEERING_REVIEWED = "engineering_reviewed"
CLINICIAN_REVIEWED = "clinician_reviewed"

# ---------------------------------------------------------------------------
# Salience filtering constants
# ---------------------------------------------------------------------------

ROUTINE_NEGATIVE_TYPES: frozenset[str] = frozenset({})

LOW_SALIENCE_TYPES: frozenset[str] = frozenset({
    "device_or_line",
})

INACTIVE_ASSERTIONS: frozenset[str] = frozenset({
    "absent",
    "not_mentioned",
})

SALIENT_CHANGES: frozenset[str] = frozenset({
    "new",
    "increased",
    "decreased",
    "resolved",
    "recurrent",
})

# ---------------------------------------------------------------------------
# Body-region groups (coarse)
# ---------------------------------------------------------------------------

_ANATOMY_GROUPS: dict[str, frozenset[str]] = {
    "chest": frozenset({
        "chest", "lung", "thorax", "pleura", "mediastinum",
        "pulmonary_artery", "heart", "cardiac",
        "left_ventricle", "right_ventricle", "left_atrium", "right_atrium",
        "aortic_valve", "mitral_valve", "pericardial",
    }),
    "abdomen": frozenset({
        "abdomen", "liver", "hepatic", "peritoneum", "bowel", "gi",
        "kidney", "renal", "spleen", "pancreas", "gallbladder",
        "adrenal", "retroperitoneum",
    }),
    "pelvis": frozenset({
        "pelvis", "bladder", "uterus", "ovary", "prostate",
    }),
    "brain": frozenset({
        "brain", "head", "intracranial", "mri", "ct_head",
        "cerebellum", "brainstem",
    }),
    "spine": frozenset({
        "spine", "vertebra", "vertebral", "spinal",
    }),
    "bone": frozenset({
        "bone", "rib", "skull", "extremity", "femur", "humerus", "clavicle",
        "scapula", "sternum",
    }),
    "neck": frozenset({
        "neck", "thyroid", "parotid", "oropharynx", "larynx",
    }),
    "soft_tissue": frozenset({
        "soft_tissue", "body_wall", "subcutaneous", "muscle",
    }),
    "vessel": frozenset({
        "vein", "artery", "aorta", "vena_cava", "deep_vein",
    }),
}

# ---------------------------------------------------------------------------
# Organ-level canonical families (for same-organ matching)
# ---------------------------------------------------------------------------

_ORGAN_FAMILIES: dict[str, frozenset[str]] = {
    "lung": frozenset({"lung", "pulmonary", "bronchus", "airway", "trachea"}),
    "liver": frozenset({"liver", "hepatic"}),
    "kidney": frozenset({"kidney", "renal"}),
    "pancreas": frozenset({"pancreas", "pancreatic"}),
    "spleen": frozenset({"spleen"}),
    "adrenal": frozenset({"adrenal", "suprarenal"}),
    "gallbladder": frozenset({"gallbladder", "biliary", "bile_duct", "cbd"}),
    "heart": frozenset({"heart", "cardiac", "pericardial", "myocardium"}),
    "brain": frozenset({"brain", "cerebral", "cerebellum", "brainstem", "intracranial"}),
    "bone": frozenset({"bone", "osseous", "skeletal"}),
    "lymph_node": frozenset({"lymph_node", "lymphadenopathy", "nodal"}),
    "peritoneum": frozenset({"peritoneum", "peritoneal", "ascites"}),
    "pleura": frozenset({"pleura", "pleural", "pleural_space"}),
    "bowel": frozenset({"bowel", "colon", "small_bowel", "duodenum", "rectum", "sigmoid", "gi"}),
}

# ---------------------------------------------------------------------------
# Organ adjacency rules (clinically meaningful pairings)
# ---------------------------------------------------------------------------

_ORGAN_ADJACENCY: dict[str, frozenset[str]] = {
    "liver": frozenset({"gallbladder", "bile_duct", "cbd", "duodenum", "adrenal", "kidney", "spleen"}),
    "gallbladder": frozenset({"liver", "pancreas", "duodenum"}),
    "pancreas": frozenset({"duodenum", "spleen", "gallbladder", "stomach", "bile_duct"}),
    "spleen": frozenset({"pancreas", "kidney", "stomach", "liver", "diaphragm"}),
    "kidney": frozenset({"adrenal", "ureter", "spleen", "liver", "pancreas"}),
    "adrenal": frozenset({"kidney", "liver"}),
    "stomach": frozenset({"esophagus", "duodenum", "pancreas", "spleen"}),
    "duodenum": frozenset({"stomach", "pancreas", "liver", "gallbladder", "small_bowel"}),
    "colon": frozenset({"rectum", "small_bowel", "appendix"}),
    "rectum": frozenset({"colon", "bladder", "prostate", "uterus"}),
    "lung": frozenset({"pleura", "mediastinum", "bronchus", "trachea", "pulmonary_artery", "heart"}),
    "pleura": frozenset({"lung", "chest_wall", "rib"}),
    "mediastinum": frozenset({"lung", "heart", "trachea", "esophagus", "lymph_node"}),
    "heart": frozenset({"lung", "mediastinum", "pericardium", "pulmonary_artery"}),
    "bladder": frozenset({"prostate", "uterus", "rectum"}),
    "prostate": frozenset({"bladder", "rectum", "seminal_vesicle"}),
    "uterus": frozenset({"ovary", "bladder", "cervix", "rectum"}),
    "brain": frozenset({"meninges", "ventricle", "skull"}),
    "bone": frozenset({"joint", "soft_tissue", "muscle"}),
    "spine": frozenset({"vertebra", "spinal", "nerve_root"}),
}


# ---------------------------------------------------------------------------
# dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrackRelationship:
    """One edge in the cross-track relationship graph."""

    source_track_key: str
    target_track_key: str
    relationship_type: str       # FINDING_PROGRESSION | STATUS_COEVOLUTION | ANATOMICAL_RELATIONSHIP | EVIDENCE_PROXIMITY
    edge_class: str              # "observed" | "inferred" | "adjudicated"
    strength: float              # 0.0-1.0
    evidence: list[str]          # report IDs / intervals / anatomy labels
    direction: str               # "bidirectional" | "forward"
    scope: str                   # "track_level"
    review_status: str           # "unreviewed" | "engineering_reviewed" | "clinician_reviewed"
    subtype: str = ""            # progression subtype / coevolution direction / polarity


# ---------------------------------------------------------------------------
# Salience helpers
# ---------------------------------------------------------------------------

def _salient_event_keys(track: dict[str, Any]) -> set[str]:
    """Return report IDs where this track has a salient event."""
    keys: set[str] = set()
    for event in track.get("events", []):
        if event.get("review_only"):
            continue
        assertion = str(event.get("assertion", "")).lower()
        temporal = str(event.get("temporal_change", "")).lower()
        if assertion in INACTIVE_ASSERTIONS and temporal not in SALIENT_CHANGES:
            continue
        rid = str(event.get("source_report_id", ""))
        if rid:
            keys.add(rid)
    return keys


def _is_salient_track(track: dict[str, Any]) -> bool:
    """Return True if the track has at least one non-review, salient event."""
    for event in track.get("events", []):
        if event.get("review_only"):
            continue
        assertion = str(event.get("assertion", "")).lower()
        temporal = str(event.get("temporal_change", "")).lower()
        if assertion not in INACTIVE_ASSERTIONS or temporal in SALIENT_CHANGES:
            return True
    return False


def _anatomy_group(anatomy: str) -> str:
    """Map a normalized anatomy string to its broad body region group."""
    a = anatomy.lower().strip()
    for group, members in _ANATOMY_GROUPS.items():
        if a in members or any(m in a for m in members if len(m) > 3):
            return group
    return a


def _canonical_organ(anatomy: str) -> str:
    """Map anatomy string to its canonical organ family."""
    a = anatomy.lower().strip()
    for organ, members in _ORGAN_FAMILIES.items():
        if a in members or any(m in a for m in members if len(m) > 3):
            return organ
    return a


def _adjacent_organs(organ_a: str, organ_b: str) -> bool:
    """Check if two canonical organ families are clinically adjacent."""
    if organ_a == organ_b:
        return False  # same organ is handled at higher strength tier, not adjacency
    adj = _ORGAN_ADJACENCY.get(organ_a, frozenset())
    if organ_b in adj:
        return True
    adj = _ORGAN_ADJACENCY.get(organ_b, frozenset())
    return organ_a in adj


def _temporal_direction(temporal_change: str) -> str:
    """Categorize temporal_change into a direction for coevolution."""
    t = temporal_change.lower()
    if t in ("new", "increased", "progressed", "worsened"):
        return "worsening"
    if t in ("decreased", "resolved", "improved"):
        return "improving"
    if t in ("stable", "unchanged", "", "not_stated"):
        return "stable"
    return "stable"


def _progression_subtype(temporal_change: str) -> str:
    """Map temporal_change to a progression subtype label."""
    t = temporal_change.lower()
    if t in ("stable", "unchanged"):
        return "stable"
    if t in ("new", "newly_developed"):
        return "new"
    if t in ("increased", "progressed", "worsened"):
        return "increased"
    if t in ("decreased", "improved"):
        return "decreased"
    if t in ("resolved", "resolved"):
        return "resolved"
    return "unknown"


# ---------------------------------------------------------------------------
# Edge builders
# ---------------------------------------------------------------------------

def _compute_finding_progression(
    tracks: dict[str, dict[str, Any]],
) -> list[TrackRelationship]:
    """Build FINDING_PROGRESSION edges: same-track temporal chain across reports."""
    edges: list[TrackRelationship] = []

    for track_key, track in tracks.items():
        events = track.get("events", [])
        if len(events) < 2:
            continue

        # Filter review-only events and sort by report order (natural sort on report_N).
        valid_events = [
            e for e in events
            if not e.get("review_only")
            and str(e.get("source_report_id", ""))
        ]

        def _report_order(event: dict[str, Any]) -> int:
            rid = str(event.get("source_report_id", ""))
            try:
                return int(rid.replace("report_", ""))
            except (ValueError, AttributeError):
                return 0

        valid_events.sort(key=_report_order)

        for i in range(len(valid_events) - 1):
            current = valid_events[i]
            next_ev = valid_events[i + 1]
            current_rid = str(current.get("source_report_id", ""))
            next_rid = str(next_ev.get("source_report_id", ""))

            temporal = str(next_ev.get("temporal_change", "")).lower()
            subtype = _progression_subtype(temporal)

            edges.append(TrackRelationship(
                source_track_key=track_key,
                target_track_key=track_key,
                relationship_type=FINDING_PROGRESSION,
                edge_class=OBSERVED,
                strength=1.0,
                evidence=[current_rid, next_rid],
                direction="forward",
                scope="track_level",
                review_status=UNREVIEWED,
                subtype=subtype,
            ))

    return edges


def _compute_status_coevolution(
    tracks: dict[str, dict[str, Any]],
) -> list[TrackRelationship]:
    """Build STATUS_COEVOLUTION edges: tracks whose status moves together."""
    edges: list[TrackRelationship] = []
    track_keys = list(tracks.keys())

    # Build per-track report-interval direction map.
    # track_key -> {(report_id, next_report_id): direction}
    track_intervals: dict[str, dict[tuple[str, str], str]] = {}

    for tk in track_keys:
        events = [
            e for e in tracks[tk].get("events", [])
            if not e.get("review_only") and str(e.get("source_report_id", ""))
        ]

        def _report_order(event: dict[str, Any]) -> int:
            rid = str(event.get("source_report_id", ""))
            try:
                return int(rid.replace("report_", ""))
            except (ValueError, AttributeError):
                return 0

        events.sort(key=_report_order)
        intervals: dict[tuple[str, str], str] = {}
        for i in range(len(events) - 1):
            cur_rid = str(events[i].get("source_report_id", ""))
            nxt_rid = str(events[i + 1].get("source_report_id", ""))
            nxt_temporal = str(events[i + 1].get("temporal_change", "")).lower()
            intervals[(cur_rid, nxt_rid)] = _temporal_direction(nxt_temporal)
        track_intervals[tk] = intervals

    for i in range(len(track_keys)):
        for j in range(i + 1, len(track_keys)):
            a_key, b_key = track_keys[i], track_keys[j]
            # Only compare across different finding types (same-type coevolution
            # is already captured by FINDING_PROGRESSION).
            if tracks[a_key].get("finding_type") == tracks[b_key].get("finding_type"):
                continue

            intervals_a = track_intervals[a_key]
            intervals_b = track_intervals[b_key]

            shared_intervals = set(intervals_a.keys()) & set(intervals_b.keys())
            if len(shared_intervals) < 2:
                continue

            match_count: dict[str, int] = {"co_worsening": 0, "co_improving": 0, "co_stable": 0}
            evidence: list[dict[str, str]] = []

            for interval in sorted(shared_intervals):
                dir_a = intervals_a[interval]
                dir_b = intervals_b[interval]
                if dir_a == dir_b:
                    if dir_a == "worsening":
                        match_count["co_worsening"] += 1
                    elif dir_a == "improving":
                        match_count["co_improving"] += 1
                    elif dir_a == "stable":
                        match_count["co_stable"] += 1
                    evidence.append({
                        "interval": f"{interval[0]}->{interval[1]}",
                        "direction": dir_a,
                    })

            total_matches = sum(match_count.values())
            if total_matches == 0:
                continue

            dominant_subtype = max(match_count, key=match_count.get)  # type: ignore[arg-type]
            strength = round(total_matches / len(shared_intervals), 4)

            edges.append(TrackRelationship(
                source_track_key=a_key,
                target_track_key=b_key,
                relationship_type=STATUS_COEVOLUTION,
                edge_class=OBSERVED,
                strength=strength,
                evidence=[e["interval"] for e in evidence],
                direction="bidirectional",
                scope="track_level",
                review_status=UNREVIEWED,
                subtype=dominant_subtype,
            ))

    return edges


def _compute_anatomical_relationship(
    tracks: dict[str, dict[str, Any]],
) -> list[TrackRelationship]:
    """Build ANATOMICAL_RELATIONSHIP edges with 3-tier organ-level granularity.

    Tiers:
      - same_organ (1.0): both anatomies normalize to the same canonical organ family
      - adjacent (0.8): anatomies are in adjacent/contained organs within the same body region
      - same_region (0.6): same coarse body region group, but non-adjacent organs
    """
    edges: list[TrackRelationship] = []
    track_keys = list(tracks.keys())

    anat_data: dict[str, tuple[str, str, str]] = {}
    for k in track_keys:
        anatomy = str(tracks[k].get("anatomy", "")).lower()
        anat_data[k] = (anatomy, _canonical_organ(anatomy), _anatomy_group(anatomy))

    for i in range(len(track_keys)):
        for j in range(i + 1, len(track_keys)):
            a_key, b_key = track_keys[i], track_keys[j]
            a_anat, a_organ, a_group = anat_data[a_key]
            b_anat, b_organ, b_group = anat_data[b_key]

            # Skip generic/unmapped anatomies.
            if a_anat in ("any", "unknown", "") or b_anat in ("any", "unknown", ""):
                continue

            # Tier 1: same canonical organ family.
            if a_organ == b_organ and a_organ not in ("", "any", "unknown"):
                strength = 1.0
                tier = "same_organ"
            # Tier 2: adjacent organs.
            elif a_group == b_group and a_group not in ("any", "unknown", ""):
                if a_organ and b_organ and _adjacent_organs(a_organ, b_organ):
                    strength = 0.8
                    tier = "adjacent"
                else:
                    strength = 0.6
                    tier = "same_region"
            else:
                continue

            edges.append(TrackRelationship(
                source_track_key=a_key,
                target_track_key=b_key,
                relationship_type=ANATOMICAL_RELATIONSHIP,
                edge_class=OBSERVED,
                strength=round(strength, 4),
                evidence=[f"anatomy:{a_anat}", f"anatomy:{b_anat}"],
                direction="bidirectional",
                scope="track_level",
                review_status=UNREVIEWED,
                subtype=tier,
            ))
    return edges


def _compute_clinical_association(
    tracks: dict[str, dict[str, Any]],
) -> list[TrackRelationship]:
    """Build EVIDENCE_PROXIMITY edges: evidence-span proximity + assertion polarity.

    Polarity filtering:
      - present+present: both findings present, mentioned near each other → co_present
      - present+absent / absent+present: one present, one ruled out → present_with_negative
      - absent+absent: both ruled out → *no edge* (not clinically informative)

    Span threshold: 200 chars same as v1.
    """
    edges: list[TrackRelationship] = []
    track_keys = list(tracks.keys())

    report_events: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for k in track_keys:
        for event in tracks[k].get("events", []):
            if event.get("review_only"):
                continue
            rid = str(event.get("source_report_id", ""))
            if not rid:
                continue
            report_events.setdefault(rid, []).append((k, event))

    for rid, events in report_events.items():
        if len(events) < 2:
            continue
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a_key, a_ev = events[i]
                b_key, b_ev = events[j]
                if a_key == b_key:
                    continue

                # Polarity check: filter absent+absent pairs.
                a_assert = str(a_ev.get("assertion", "")).lower()
                b_assert = str(b_ev.get("assertion", "")).lower()
                if a_assert in ("absent", "not_mentioned") and b_assert in ("absent", "not_mentioned"):
                    continue

                if a_assert in ("absent", "not_mentioned"):
                    polarity = "present_with_negative"
                elif b_assert in ("absent", "not_mentioned"):
                    polarity = "present_with_negative"
                else:
                    polarity = "co_present"

                a_start = a_ev.get("evidence_span_start", -1)
                a_end = a_ev.get("evidence_span_end", -1)
                b_start = b_ev.get("evidence_span_start", -1)
                b_end = b_ev.get("evidence_span_end", -1)

                if a_start >= 0 and a_end >= 0 and b_start >= 0 and b_end >= 0:
                    distance = min(
                        abs(b_start - a_end),
                        abs(a_start - b_end),
                        abs(b_start - a_start),
                    )
                    if distance > 200:
                        continue
                    strength = max(0.0, 1.0 - distance / 200.0)
                else:
                    strength = 0.5

                edges.append(TrackRelationship(
                    source_track_key=a_key,
                    target_track_key=b_key,
                    relationship_type=EVIDENCE_PROXIMITY,
                    edge_class=OBSERVED,
                    strength=round(strength, 4),
                    evidence=[rid],
                    direction="bidirectional",
                    scope="track_level",
                    review_status=UNREVIEWED,
                    subtype=polarity,
                ))

    return edges


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_track_graph(
    tracks: dict[str, dict[str, Any]],
    *,
    include_routine_negatives: bool = False,
    include_clinical_association_rules: bool = True,
    temporal_threshold: float = 0.2,
    min_shared_reports: int = 2,
) -> dict[str, Any]:
    """Build a cross-track relationship graph from a track dict.

    Args:
        tracks: ``{track_key: track_dict}`` as produced by the frame linker.
        include_routine_negatives: If False (default), filter out tracks where
            every event has assertion ``absent`` / ``not_mentioned`` and no
            salient temporal change.
        include_clinical_association_rules: If True (default in v2), include
            EVIDENCE_PROXIMITY edges. If False, skip them for speed/comparability.
        temporal_threshold: Unused in v2 (retained for API compatibility).
        min_shared_reports: Unused in v2 (retained for API compatibility).

    Returns:
        A dict with keys ``edges`` (list of serializable TrackRelationship
        dicts) and ``graph_metadata`` (summary statistics).
    """
    # Filter to salient tracks.
    if include_routine_negatives:
        active_tracks = dict(tracks)
    else:
        active_tracks = {
            k: v for k, v in tracks.items()
            if _is_salient_track(v)
            and str(v.get("finding_type", "")).lower() not in LOW_SALIENCE_TYPES
        }

    progression_edges = _compute_finding_progression(active_tracks)
    anatomical_edges = _compute_anatomical_relationship(active_tracks)
    coevolution_edges = _compute_status_coevolution(active_tracks)
    clinical_edges = _compute_clinical_association(active_tracks) if include_clinical_association_rules else []

    all_edges = progression_edges + coevolution_edges + anatomical_edges + clinical_edges

    # Count edges per type.
    type_counts: dict[str, int] = {}
    subtype_counts: dict[str, int] = {}
    for edge in all_edges:
        type_counts[edge.relationship_type] = type_counts.get(edge.relationship_type, 0) + 1
        if edge.subtype:
            subtype_counts[edge.subtype] = subtype_counts.get(edge.subtype, 0) + 1

    # Compute density (excluding self-loop progression edges).
    non_self_edges = [e for e in all_edges if e.relationship_type != FINDING_PROGRESSION]
    n_tracks = len(active_tracks)
    max_possible = n_tracks * (n_tracks - 1) / 2 if n_tracks > 1 else 0
    density = len(non_self_edges) / max_possible if max_possible > 0 else 0.0

    return {
        "edges": [
            {
                "source": edge.source_track_key,
                "target": edge.target_track_key,
                "type": edge.relationship_type,
                "subtype": edge.subtype,
                "edge_class": edge.edge_class,
                "strength": edge.strength,
                "evidence": edge.evidence,
                "direction": edge.direction,
                "scope": edge.scope,
                "review_status": edge.review_status,
            }
            for edge in all_edges
        ],
        "graph_metadata": {
            "n_tracks_total": len(tracks),
            "n_tracks_active": n_tracks,
            "n_edges_total": len(all_edges),
            "n_progression_edges": type_counts.get(FINDING_PROGRESSION, 0),
            "n_coevolution_edges": type_counts.get(STATUS_COEVOLUTION, 0),
            "n_anatomical_edges": type_counts.get(ANATOMICAL_RELATIONSHIP, 0),
            "n_evidence_proximity_edges": type_counts.get(EVIDENCE_PROXIMITY, 0),
            "edge_counts_by_type": type_counts,
            "edge_counts_by_subtype": subtype_counts,
            "density": round(density, 6),
            "filter_routine_negatives": not include_routine_negatives,
            "track_graph_version": "v2",
            "edge_classes": [OBSERVED],
            "review_status": UNREVIEWED,
        },
    }
