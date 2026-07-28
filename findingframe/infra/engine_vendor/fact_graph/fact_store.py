"""
Append-only fact graph store with SQLite as the primary backend.

JSON files are still exported as compatibility snapshots for existing readers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from entity_grounding.entity_grounder import infer_body_region

from .db_store import SQLiteFactStore
from .migrations import migrate_graph_payload
from .schema import CertaintyPoint, EntityNode, Event, FactGraph, Measurement


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _evidence_text_from_finding(finding: dict[str, Any], measurement: Measurement) -> str | None:
    """Best-effort exact evidence snippet to persist with an event."""
    evidence = _safe_str(finding.get("evidence_text")).strip()
    if evidence and evidence != "negated finding":
        return evidence
    # Fix #3: "negated finding" placeholder is not real evidence.
    # Treat it the same as empty — let span recovery try harder.
    negation = _safe_str(finding.get("negation_language")).strip()
    if negation and negation != "negated finding":
        return negation
    if measurement.raw_text:
        return measurement.raw_text
    return None


def _extract_sentence(report_text: str, span_start: int, span_end: int) -> str:
    """Extract the full sentence containing the given character span."""
    if span_start < 0 or span_end <= span_start or span_end > len(report_text):
        return ""
    start = max(
        report_text.rfind(". ", 0, span_start),
        report_text.rfind("\n", 0, span_start),
        0,
    )
    if start > 0:
        if report_text[start:start+2] == ". ":
            start += 2
        elif report_text[start] == "\n":
            start += 1
    end = report_text.find(". ", span_end)
    if end == -1:
        end = report_text.find("\n", span_end)
    if end == -1:
        end = len(report_text)
    else:
        end += 1
    return report_text[start:end].strip()


def _certainty_to_score(label: str, default: float | None = None) -> float:
    if default is not None:
        try:
            return max(0.0, min(float(default), 1.0))
        except Exception:
            pass
    label_norm = (label or "").strip().lower()
    mapping = {
        "confirmed": 0.96,
        "suspected": 0.8,
        "differential": 0.6,
        "uncertain": 0.35,
        "negative": 0.99,
    }
    return mapping.get(label_norm, 0.5)


def derive_entity_status(events: list[Event]) -> str:
    """Derive current entity status from the latest dated evidence group."""
    if not events:
        return "uncertain"

    sorted_events = sorted(events, key=lambda e: (e.date, e.event_id))
    latest_date = sorted_events[-1].date
    latest_events = [event for event in sorted_events if event.date == latest_date]
    if not latest_events:
        return "uncertain"

    latest_all_negated = all(event.is_negated for event in latest_events)
    latest_any_negated = any(event.is_negated for event in latest_events)
    latest_any_positive = any(not event.is_negated for event in latest_events)

    if latest_all_negated:
        had_prior_positive = any(
            not event.is_negated for event in sorted_events if event.date < latest_date
        )
        return "resolved" if had_prior_positive else "absent"

    if latest_any_negated and latest_any_positive:
        return "mixed"

    if any(event.trend == "resolved" for event in latest_events):
        return "resolved"

    latest_certainties = {event.certainty_label for event in latest_events}
    if latest_certainties.intersection({"suspected", "differential", "uncertain"}):
        return "uncertain"

    return "active"


def _entity_type_from_finding(canonical_name: str, finding_type: str) -> str:
    cname = canonical_name.lower()
    ftype = (finding_type or "").lower()
    if cname.startswith("primary_") or "primary" in ftype:
        return "primary_tumor"
    if "metastasis" in cname or "metasta" in ftype:
        return "metastasis"
    if "lymph" in cname or "node" in cname:
        return "lymph_node"
    return "finding"


def _clean_evidence_surface(text: str) -> str:
    cleaned = _safe_str(text).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(
        r"^(?:there is|there are)\s+no\s+|^no evidence of\s+|^no\s+|^without\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:is seen|are seen|identified|noted|present|apparent)\.?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" .")


def _override_generic_canonical(
    canonical_name: str,
    radlex_id: Any,
    snomed_id: Any,
    finding: dict[str, Any],
) -> tuple[str, Any, Any]:
    if canonical_name != "finding_bone":
        return canonical_name, radlex_id, snomed_id

    evidence = _clean_evidence_surface(
        finding.get("evidence_text") or finding.get("negation_language") or ""
    )
    lowered = evidence.lower()
    if not evidence:
        return canonical_name, radlex_id, snomed_id
    if "osseous abnormality" in lowered or "bone abnormality" in lowered:
        return "finding_osseous_abnormality", radlex_id, snomed_id

    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if not slug:
        return canonical_name, radlex_id, snomed_id
    return f"finding_{slug}", None, None


# ---------------------------------------------------------------------------
# G5: Deterministic span recovery helper
# ---------------------------------------------------------------------------

def _recover_span_from_evidence(entity_name: str, evidence_text: str) -> tuple[int, int]:
    """
    Locate *entity_name* tokens inside *evidence_text* and return the
    (start, end) character offsets of the tightest matching window.

    Strategy (in order of preference):
    1. Direct case-insensitive substring match.
    2. Whole-word token match (exact words, 3+ chars).
    3. Prefix match fallback (4+ char prefix of each token, handles
       morphological variants like 'osteophytes' vs 'osteophytosis').

    For negated findings the entity name is the clinical concept ("hemorrhage"),
    NOT the negation phrase ("No evidence of hemorrhage").  Because we search
    for the entity name tokens specifically, negation prefixes are automatically
    excluded from the returned span (V-G5-06, V-G5-07).

    Returns (-1, -1) on any failure — no exception raised (V-G5-08).
    """
    if not entity_name or not evidence_text:
        return -1, -1

    ent_norm = entity_name.strip().lower()
    ev_norm  = evidence_text.lower()

    # Strategy 1: Direct substring match
    idx = ev_norm.find(ent_norm)
    if idx >= 0:
        return idx, idx + len(ent_norm)

    # Strategy 2: Whole-word token match
    tokens = [t for t in re.findall(r'\b[a-z]{3,}\b', ent_norm)]
    if not tokens:
        return -1, -1

    positions: list[tuple[int, int]] = []
    for token in tokens:
        m = re.search(r'\b' + re.escape(token) + r'\b', ev_norm)
        if m:
            positions.append((m.start(), m.end()))

    # If at least half the tokens matched, build the covering window
    if len(positions) >= max(1, len(tokens) // 2):
        return min(p[0] for p in positions), max(p[1] for p in positions)

    # Strategy 3: Prefix match — handles morphological variants
    # Use the 4+ character prefix of each entity token to find morphological siblings
    PREFIX_LEN = 5
    prefix_positions: list[tuple[int, int]] = []
    for token in tokens:
        if len(token) < PREFIX_LEN:
            continue
        prefix = re.escape(token[:PREFIX_LEN])
        m = re.search(r'\b' + prefix + r'\w*\b', ev_norm)
        if m:
            prefix_positions.append((m.start(), m.end()))

    if len(prefix_positions) >= max(1, len(tokens) // 2):
        return min(p[0] for p in prefix_positions), max(p[1] for p in prefix_positions)

    return -1, -1


# ---------------------------------------------------------------------------




_LATERALITY_LEFT = re.compile(r"\bleft\b", re.IGNORECASE)
_LATERALITY_RIGHT = re.compile(r"\bright\b", re.IGNORECASE)
_LATERALITY_BILATERAL = re.compile(r"\bbilateral\b", re.IGNORECASE)

# Anatomical subsite keywords (directional / lobe qualifiers)
_SUBSITE_TOKENS = frozenset([
    "upper", "lower", "middle", "medial", "lateral",
    "anterior", "posterior", "superior", "inferior",
    "lobe", "apical", "basal", "central", "peripheral",
])


def _extract_laterality(text: str) -> str | None:
    """
    Return 'bilateral', 'left', 'right', or None from a free-text string.
    'bilateral' takes priority over 'left' or 'right'.
    """
    t = text.lower()
    if _LATERALITY_BILATERAL.search(t):
        return "bilateral"
    if _LATERALITY_LEFT.search(t):
        return "left"
    if _LATERALITY_RIGHT.search(t):
        return "right"
    return None


def _extract_subsite(text: str) -> frozenset[str]:
    """
    Return the set of anatomical subsite tokens present in *text*.
    Only non-empty sets are considered significant.
    """
    tokens = set(re.findall(r"\b\w+\b", text.lower()))
    return frozenset(tokens & _SUBSITE_TOKENS)


def _has_conflicting_laterality_or_subsite(
    entity_a: "EntityNode",
    entity_b: "EntityNode",
) -> bool:
    """
    Return True when merging entity_a and entity_b would silently collapse
    anatomically distinct findings.

    Rules (all applied to the combined search text from canonical_name +
    anatomical_site so that laterality expressed in either field is captured):

    1. If neither entity has a laterality signal → allow (return False).
    2. If one entity has no laterality signal → allow (return False).
    3. If both have the same laterality:
       - If both have subsite tokens AND those tokens differ → block (return True).
       - Otherwise → allow (return False).
    4. If laterality signals differ (left vs right, bilateral vs unilateral) → block.
    """
    def _text(e: "EntityNode") -> str:
        return f"{e.canonical_name or ''} {e.anatomical_site or ''}".lower()

    text_a = _text(entity_a)
    text_b = _text(entity_b)

    lat_a = _extract_laterality(text_a)
    lat_b = _extract_laterality(text_b)

    # Rule 1 & 2: either entity has no laterality → allow
    if lat_a is None or lat_b is None:
        return False

    # Rule 4: different laterality → block
    if lat_a != lat_b:
        return True

    # Rule 3: same laterality — check subsite
    sub_a = _extract_subsite(text_a)
    sub_b = _extract_subsite(text_b)
    if sub_a and sub_b and sub_a != sub_b:
        return True  # same side, different lobe/region → block

    return False


# ---------------------------------------------------------------------------


class FactStore:
    def __init__(
        self,
        subject_id: str,
        output_dir: str = "./outputs/patient_gcs",
        db_path: str | None = None,
        radlex_hierarchy: dict[str, list[str]] | None = None,
    ):
        self.subject_id = str(subject_id)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.graph_path = self.output_dir / f"subject_{self.subject_id}_fact_graph.json"
        if db_path:
            resolved_db_path = Path(db_path)
        elif self.output_dir == Path("./outputs/patient_gcs"):
            resolved_db_path = Path("data") / "fact_graphs.db"
        else:
            resolved_db_path = self.output_dir / "fact_graphs.db"
        self.sqlite_store = SQLiteFactStore(db_path=resolved_db_path)
        self.graph = FactGraph(subject_id=self.subject_id)
        # radlex_hierarchy: maps RID → list of parent RIDs for hierarchy merging
        self._radlex_hierarchy = radlex_hierarchy or {}
        # G4: diagnostic counter — number of same-RID merges blocked by laterality guard
        self.blocked_merge_count: int = 0

    def load(self) -> FactGraph:
        sqlite_payload = self.sqlite_store.load_fact_graph(self.subject_id)
        if sqlite_payload:
            self.graph = FactGraph.model_validate(migrate_graph_payload(sqlite_payload))
            return self.graph

        if not self.graph_path.exists():
            return self.graph

        raw = json.loads(self.graph_path.read_text(encoding="utf-8", errors="ignore"))
        migrated = migrate_graph_payload(raw)
        self.graph = FactGraph.model_validate(migrated)
        # One-way backfill into SQLite so future loads use the primary store.
        self.sqlite_store.save_fact_graph(self.graph.model_dump(mode="json"))
        return self.graph

    def save(self) -> str:
        self._ensure_unique_event_ids()
        self.graph.metadata["updated_at"] = datetime.now().isoformat()
        payload = self.graph.model_dump(mode="json")
        self.sqlite_store.save_fact_graph(payload)
        self.graph_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return str(self.graph_path)

    def get_entity(self, entity_id: str) -> EntityNode | None:
        return self.graph.entities.get(entity_id)

    def get_patient_graph(self) -> FactGraph:
        return self.graph

    def serialize(self) -> dict[str, Any]:
        return self.graph.model_dump(mode="json")

    def replace_graph(self, payload: dict[str, Any]) -> None:
        migrated = migrate_graph_payload(payload or {})
        if "subject_id" not in migrated:
            migrated["subject_id"] = self.subject_id
        self.graph = FactGraph.model_validate(migrated)

    def _ensure_unique_event_ids(self) -> None:
        seen: set[str] = set()
        for entity in self.graph.entities.values():
            unique_events: list[Event] = []
            for event in entity.events:
                base_id = event.event_id
                if base_id in seen:
                    suffix = 2
                    while f"{base_id}_{suffix}" in seen:
                        suffix += 1
                    event.event_id = f"{base_id}_{suffix}"
                seen.add(event.event_id)
                unique_events.append(event)
            unique_events.sort(key=lambda e: (e.date, e.event_id))
            entity.events = unique_events

    def _measurement_from_finding(self, finding: dict[str, Any]) -> Measurement:
        norm = finding.get("measurement_normalized", {})
        if isinstance(norm, dict) and (norm.get("value_mm") is not None or norm.get("is_qualitative")):
            return Measurement(
                value=norm.get("value"),
                unit=norm.get("unit"),
                normalized_mm=norm.get("value_mm"),
                is_qualitative=bool(norm.get("is_qualitative", False)),
                raw_text=norm.get("raw_text"),
                delta_mm=norm.get("delta_mm"),
            )

        measurement = finding.get("measurement", {})
        current = ""
        trend = ""
        if isinstance(measurement, dict):
            current = _safe_str(measurement.get("current", "")).strip()
            trend = _safe_str(measurement.get("trend", "")).strip()
        raw_text = current or trend or None
        # Fallback parse for values like "3.2 cm" or "32 mm"
        mm_value = None
        if raw_text:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm|in)\b", raw_text.lower())
            if m:
                value = float(m.group(1))
                unit = m.group(2)
                mm_value = value if unit == "mm" else value * 10.0 if unit == "cm" else value * 25.4
                return Measurement(
                    value=value,
                    unit=unit,
                    normalized_mm=round(mm_value, 2),
                    is_qualitative=False,
                    raw_text=raw_text,
                )
        return Measurement(raw_text=raw_text, is_qualitative=bool(trend and not mm_value))

    def _trend_from_finding(self, finding: dict[str, Any], measurement: Measurement) -> str:
        trend = ""
        measurement_raw = finding.get("measurement", {})
        if isinstance(measurement_raw, dict):
            trend = _safe_str(measurement_raw.get("trend", "")).lower()
        if not trend:
            norm = finding.get("measurement_normalized", {})
            if isinstance(norm, dict):
                trend = _safe_str(norm.get("trend", "")).lower()
        if not trend and measurement.raw_text:
            text = measurement.raw_text.lower()
            if "increas" in text or "larger" in text:
                trend = "increasing"
            elif "decreas" in text or "smaller" in text:
                trend = "decreasing"
            elif "stable" in text or "unchanged" in text:
                trend = "stable"
            elif "new" in text:
                trend = "new"
            elif "resolved" in text:
                trend = "resolved"
        mapping = {
            "increase": "increasing",
            "increased": "increasing",
            "increasing": "increasing",
            "decrease": "decreasing",
            "decreased": "decreasing",
            "decreasing": "decreasing",
            "stable": "stable",
            "unchanged": "stable",
            "new": "new",
            "resolved": "resolved",
        }
        return mapping.get(trend, "unknown")

    def append_grounded_finding(
        self,
        finding: dict[str, Any],
        grounded_entity: dict[str, Any],
        report_date: str,
        hadm_id: str,
        report_id: str,
        modality: str,
        event_index: int,
    ) -> Event:
        entity_id = _safe_str(grounded_entity.get("canonical_name")).strip() or "finding_unspecified_entity"
        radlex_id = grounded_entity.get("radlex_id")
        radlex_preferred_label = grounded_entity.get("radlex_label")
        snomed_id = grounded_entity.get("snomed_id")
        entity_id, radlex_id, snomed_id = _override_generic_canonical(
            entity_id,
            radlex_id,
            snomed_id,
            finding,
        )
        date = _safe_str(report_date)
        certainty_label = _safe_str(finding.get("certainty", "unknown")).strip().lower() or "unknown"
        certainty = _certainty_to_score(
            certainty_label,
            default=finding.get("confidence_score"),
        )
        anatomical_site = _safe_str(finding.get("anatomical_location", "")).strip() or None
        # P3: cross-anatomy collapse fix — disambiguate entity IDs for
        # findings where body-region merging is dangerous (fracture,
        # degenerative changes, dislocation, etc.)
        from extraction.canonical_vocabulary import ANATOMY_DISAMBIGUATED_ENTITIES

        if anatomical_site and entity_id in ANATOMY_DISAMBIGUATED_ENTITIES:
            site_slug = re.sub(r"[^a-z0-9]+", "_", anatomical_site.lower()).strip("_")
            if site_slug:
                entity_id = f"{entity_id}_{site_slug}"
        body_region = infer_body_region(entity_id, anatomical_site)
        measurement = self._measurement_from_finding(finding)
        evidence_text = _evidence_text_from_finding(finding, measurement)
        trend = self._trend_from_finding(finding, measurement)

        # Negation propagation (Phase 2)
        is_negated = bool(finding.get("is_negated", False))
        negation_language = _safe_str(finding.get("negation_language")) or None

        node = self.graph.entities.get(entity_id)
        if node is None:
            node = EntityNode(
                entity_id=entity_id,
                canonical_name=entity_id,
                radlex_id=radlex_id,
                radlex_preferred_label=radlex_preferred_label,
                snomed_id=snomed_id,
                entity_type=_entity_type_from_finding(
                    entity_id,
                    _safe_str(finding.get("finding_type")),
                ),
                anatomical_site=anatomical_site,
                body_region=body_region,
                first_documented=date,
                last_documented=date,
                status="uncertain" if certainty_label in {"suspected", "differential", "uncertain"} else "active",
            )
            self.graph.entities[entity_id] = node
        else:
            if date and date < node.first_documented:
                node.first_documented = date
            if date and date > node.last_documented:
                node.last_documented = date
            if anatomical_site and not node.anatomical_site:
                node.anatomical_site = anatomical_site
            if (not node.body_region or node.body_region == "other") and body_region:
                node.body_region = body_region
            if radlex_id and not node.radlex_id:
                node.radlex_id = radlex_id
            if radlex_preferred_label and not node.radlex_preferred_label:
                node.radlex_preferred_label = radlex_preferred_label
            if snomed_id and not node.snomed_id:
                node.snomed_id = snomed_id

        event_id = f"evt_{self.subject_id}_{_safe_str(report_id)}_{event_index:03d}"
        existing_event_ids = {event.event_id for event in node.events}
        if event_id in existing_event_ids:
            # Deterministic suffix if same report gets reprocessed with collisions.
            suffix = len(existing_event_ids) + 1
            event_id = f"{event_id}_{suffix}"

        # Provenance fields (v14)
        span_start = int(finding.get("span_start", -1) or -1)
        span_end = int(finding.get("span_end", -1) or -1)

        # G5: deterministic span recovery for LLM-extracted findings whose
        # span was not set by the rule extractor.
        if span_start == -1 or span_end == -1:
            entity_surface = _safe_str(finding.get("entity", "")).strip()
            evidence       = _safe_str(evidence_text).strip()
            if entity_surface and evidence:
                span_start, span_end = _recover_span_from_evidence(
                    entity_surface, evidence
                )

        # P5: evidence-text recovery from source report when span is valid
        # but evidence text was not populated (LLM may omit evidence_text
        # even when span_start / span_end are returned).
        # Fix #0: use sentence-level extraction instead of character-range
        # to avoid fragments like "ree fluid" or "nfarct".
        if (not evidence_text or not evidence_text.strip()) and span_start >= 0 and span_end > span_start:
            source_report = _safe_str(finding.get("_source_report_text", "")).strip()
            if source_report and span_end <= len(source_report):
                sentence = _extract_sentence(source_report, span_start, span_end)
                if sentence:
                    evidence_text = sentence
                else:
                    evidence_text = source_report[span_start:span_end]

        source = str(finding.get("source", "llm") or "llm")
        if source not in ("rule", "llm", "human"):
            source = "llm"

        event = Event(
            event_id=event_id,
            entity_id=entity_id,
            date=date,
            source_report_id=_safe_str(report_id),
            hadm_id=_safe_str(hadm_id),
            modality=modality or "OTHER",
            measurement=measurement,
            certainty=certainty,
            certainty_label=certainty_label,
            uncertainty_language=_safe_str(finding.get("temporal_qualifier")) or None,
            comparison_to_prior=_safe_str(finding.get("comparison_to_prior")) or None,
            trend=trend,
            is_negated=is_negated,
            negation_language=negation_language,
            span_start=span_start,
            span_end=span_end,
            evidence_text=evidence_text,
            source=source,
            confidence=certainty,
        )
        node.events.append(event)
        node.events.sort(key=lambda e: (e.date, e.event_id))

        certainty_point = CertaintyPoint(
            date=date,
            certainty=certainty,
            certainty_label=certainty_label,
            language_used=_safe_str(finding.get("temporal_qualifier")) or None,
        )
        cert_key = (certainty_point.date, certainty_point.certainty_label)
        seen_cert = {(p.date, p.certainty_label) for p in node.certainty_trajectory}
        if cert_key not in seen_cert:
            node.certainty_trajectory.append(certainty_point)
            node.certainty_trajectory.sort(key=lambda p: p.date)

        node.status = derive_entity_status(node.events)
        return event

    def _absorb_entity(self, target: EntityNode, source: EntityNode) -> None:
        """Move all events and metadata from source into target."""
        for event in source.events:
            if event.entity_id != target.entity_id:
                event.entity_id = target.entity_id
            if all(existing.event_id != event.event_id for existing in target.events):
                target.events.append(event)
        for point in source.certainty_trajectory:
            key = (point.date, point.certainty_label)
            if all((p.date, p.certainty_label) != key for p in target.certainty_trajectory):
                target.certainty_trajectory.append(point)
        target.first_documented = min(target.first_documented, source.first_documented)
        target.last_documented = max(target.last_documented, source.last_documented)
        if not target.anatomical_site and source.anatomical_site:
            target.anatomical_site = source.anatomical_site
        if not target.radlex_id and source.radlex_id:
            target.radlex_id = source.radlex_id
        target.events.sort(key=lambda e: (e.date, e.event_id))
        target.certainty_trajectory.sort(key=lambda p: p.date)

    @staticmethod
    def _days_between_entities(a: EntityNode, b: EntityNode) -> int | None:
        """Return the minimum days between any pair of events from a and b."""
        try:
            dates_a = [datetime.fromisoformat(e.date) for e in a.events if e.date]
            dates_b = [datetime.fromisoformat(e.date) for e in b.events if e.date]
        except (ValueError, TypeError):
            return None
        if not dates_a or not dates_b:
            return None
        return min(abs((da - db).days) for da in dates_a for db in dates_b)

    def _is_parent_or_child(self, rid_a: str, rid_b: str) -> bool:
        """Check if rid_a is a direct parent or child of rid_b in the RadLex hierarchy."""
        if not self._radlex_hierarchy:
            return False
        parents_a = self._radlex_hierarchy.get(rid_a, [])
        parents_b = self._radlex_hierarchy.get(rid_b, [])
        return rid_b in parents_a or rid_a in parents_b

    def merge_entities_by_radlex(self) -> None:
        """
        Deterministic dedupe pass with two merge windows:
        1. Same RadLex ID: merge unless laterality/subsite conflict detected (G4 guard).
        2. Parent/child RadLex IDs within 365 days: merge longitudinal chronic findings.

        Blocked merges (same RID but conflicting laterality/subsite) are counted in
        self.blocked_merge_count for diagnostic visibility.
        """
        # Pass 1: exact RadLex ID match — guarded by laterality / subsite check
        by_radlex: dict[str, list[str]] = {}
        for entity_id, entity in self.graph.entities.items():
            if entity.radlex_id:
                by_radlex.setdefault(entity.radlex_id, []).append(entity_id)

        for rid, entity_ids in by_radlex.items():
            if len(entity_ids) < 2:
                continue
            target_id = sorted(entity_ids)[0]
            target = self.graph.entities[target_id]
            for source_id in sorted(entity_ids)[1:]:
                if source_id not in self.graph.entities:
                    continue
                source = self.graph.entities[source_id]
                # G4: laterality / subsite safety guard
                if _has_conflicting_laterality_or_subsite(target, source):
                    self.blocked_merge_count += 1
                    continue
                self._absorb_entity(target, source)
                del self.graph.entities[source_id]

        # Pass 2: hierarchy-based merge (parent/child within 365 days)
        if self._radlex_hierarchy:
            merged_any = True
            while merged_any:
                merged_any = False
                entity_ids = sorted(self.graph.entities.keys())
                for i, eid_a in enumerate(entity_ids):
                    if eid_a not in self.graph.entities:
                        continue
                    entity_a = self.graph.entities[eid_a]
                    if not entity_a.radlex_id:
                        continue
                    for eid_b in entity_ids[i + 1:]:
                        if eid_b not in self.graph.entities:
                            continue
                        entity_b = self.graph.entities[eid_b]
                        if not entity_b.radlex_id:
                            continue
                        if entity_a.radlex_id == entity_b.radlex_id:
                            continue  # already handled in pass 1
                        if not self._is_parent_or_child(entity_a.radlex_id, entity_b.radlex_id):
                            continue
                        # Body region guard — for parent/child hierarchy
                        # merges, require both entities to have a known body
                        # region AND for them to match.  This prevents generic
                        # parent concepts (e.g. "effusion") from absorbing
                        # site-specific children from a different body region
                        # (e.g. joint effusion ≠ pleural effusion).
                        region_a = entity_a.body_region or "other"
                        region_b = entity_b.body_region or "other"
                        if region_a == "other" or region_b == "other" or region_a != region_b:
                            continue
                        days = self._days_between_entities(entity_a, entity_b)
                        if days is None or days > 365:
                            continue
                        # Merge: keep the entity with more events as target
                        if len(entity_a.events) >= len(entity_b.events):
                            self._absorb_entity(entity_a, entity_b)
                            del self.graph.entities[eid_b]
                        else:
                            self._absorb_entity(entity_b, entity_a)
                            del self.graph.entities[eid_a]
                        merged_any = True
                        break
                    if merged_any:
                        break
