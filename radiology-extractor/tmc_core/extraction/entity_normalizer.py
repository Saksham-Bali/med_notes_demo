"""
Agent 2: Entity Normalizer

Standardizes and merges duplicate entities across multiple radiology reports.
Uses Azure OpenAI GPT-5-mini.

Supports batched normalization for patients with many reports.
"""

import json
import os
import sys
import re
from typing import Optional, Any
from dataclasses import dataclass
from difflib import SequenceMatcher

from tmc_core.extraction.prompts import ENTITY_NORMALIZATION_PROMPT
from pathlib import Path

from tmc_core.entity_grounding.entity_grounder import infer_body_region
from tmc_core.utils.llm import create_default_llm_client, parse_json_from_text

# Maximum number of report findings to normalize in one LLM call
BATCH_SIZE = 10
AMBIGUOUS_BATCH_LIMIT = 30


@dataclass
class NormalizedEntity:
    """A normalized clinical entity with its timeline."""

    canonical_name: str
    variants_seen: list[str]
    first_documented: str
    timeline: list[dict]
    current_status: str
    certainty_evolution: list[dict]


@dataclass
class NormalizationResult:
    """Result of entity normalization across reports."""

    normalized_entities: list[NormalizedEntity]
    flagged_contradictions: list[dict]
    raw_response: str


@dataclass
class GraphDeduplicationResult:
    """Result of graph-level entity deduplication."""

    deduplicated_graph: dict[str, Any]
    merges_applied: list[dict[str, Any]]
    flagged_ambiguous_pairs: list[dict[str, Any]]
    raw_response: str


class EntityNormalizer:
    """
    Normalizes entities across multiple radiology reports using Azure OpenAI.
    Supports batched normalization: splits large finding sets into chunks
    and merges results.
    """

    def __init__(self, llm_client: Optional[Any] = None):
        """Initialize the entity normalizer with Azure OpenAI."""
        from tmc_core.utils.llm import AZURE_DEPLOYMENT
        self.llm_client = llm_client or create_default_llm_client(
            deployment=os.getenv("AZURE_DEPLOYMENT", AZURE_DEPLOYMENT)
        )

    def normalize(
        self, findings_list: list[dict], report_ids: Optional[list[str]] = None
    ) -> NormalizationResult:
        """
        Normalize entities across multiple extraction results.
        Automatically batches if findings_list has more than BATCH_SIZE items.
        """
        if len(findings_list) <= BATCH_SIZE:
            return self._normalize_batch(findings_list)

        # Batch normalization for large finding sets
        print(
            f"  Batching normalization: {len(findings_list)} report findings in chunks of {BATCH_SIZE}"
        )

        all_entities = []
        all_contradictions = []
        all_raw = []

        for i in range(0, len(findings_list), BATCH_SIZE):
            batch = findings_list[i : i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (len(findings_list) + BATCH_SIZE - 1) // BATCH_SIZE
            print(
                f"  Normalizing batch {batch_num}/{total_batches} ({len(batch)} reports)"
            )

            result = self._normalize_batch(batch)
            all_entities.extend(result.normalized_entities)
            all_contradictions.extend(result.flagged_contradictions)
            all_raw.append(result.raw_response)

        # Merge entities with same canonical names across batches
        merged_entities = self._merge_entities(all_entities)

        return NormalizationResult(
            normalized_entities=merged_entities,
            flagged_contradictions=all_contradictions,
            raw_response="\n---BATCH---\n".join(all_raw),
        )

    def deduplicate_fact_graph(
        self,
        fact_graph: dict[str, Any],
        deterministic_threshold: float = 0.88,
        ambiguous_threshold: float = 0.75,
    ) -> GraphDeduplicationResult:
        """
        Agent 2 v2 path: deduplicate entity nodes in the Fact Graph.

        Strategy:
        0) Token-majority pre-pass: ≥70% content-token overlap + same body region
           → deterministic merge regardless of overall similarity score.
           Catches pairs like "lung_volumes_low" vs "low_lung_volumes_r24" that
           fail the 0.88 threshold because of suffix noise or token reordering.
        1) Deterministic merges for very-high lexical similarity (≥0.88)
        2) Optional LLM disambiguation for high-similarity pairs (≥0.75)
        """
        graph = json.loads(json.dumps(fact_graph or {}))
        entities = graph.get("entities", {})
        if not isinstance(entities, dict) or len(entities) < 2:
            return GraphDeduplicationResult(
                deduplicated_graph=graph,
                merges_applied=[],
                flagged_ambiguous_pairs=[],
                raw_response="",
            )

        merges_applied: list[dict[str, Any]] = []

        # ── Pass 0: Token-majority merge (Week 3) ──────────────────────────────
        # If ≥70% of meaningful content tokens overlap AND same body region
        # → merge deterministically, bypassing the similarity threshold entirely.
        # This fixes the known failure mode where report-index suffixes (_r24)
        # or token reordering drops the SequenceMatcher score below 0.88.
        merges_applied.extend(self._token_majority_merges(entities))

        candidates = self._candidate_entity_pairs(entities)
        ambiguous_pairs: list[dict[str, Any]] = []

        for pair in candidates:
            score = pair["similarity_score"]
            if score >= deterministic_threshold:
                target_id, source_id = self._pick_merge_direction(
                    pair["entity_a"], pair["entity_b"], entities
                )
                if self._merge_entity_pair(
                    entities,
                    target_id=target_id,
                    source_id=source_id,
                    reason="deterministic_similarity",
                ):
                    merges_applied.append(
                        {
                            "target_entity_id": target_id,
                            "source_entity_id": source_id,
                            "reason": "deterministic_similarity",
                            "score": round(score, 3),
                        }
                    )
            elif score >= ambiguous_threshold:
                ambiguous_pairs.append(pair)

        raw_response = ""
        if ambiguous_pairs:
            llm_merges, raw_response = self._resolve_ambiguous_pairs_llm(
                ambiguous_pairs, entities
            )
            for merge in llm_merges:
                target_id = str(merge.get("target_entity_id", ""))
                source_id = str(merge.get("source_entity_id", ""))
                if not target_id or not source_id or target_id == source_id:
                    continue
                confidence = float(merge.get("confidence", 0.0) or 0.0)
                if confidence < 0.65:
                    continue
                if self._merge_entity_pair(
                    entities,
                    target_id=target_id,
                    source_id=source_id,
                    reason="llm_ambiguous_pair",
                ):
                    merges_applied.append(
                        {
                            "target_entity_id": target_id,
                            "source_entity_id": source_id,
                            "reason": "llm_ambiguous_pair",
                            "score": confidence,
                        }
                    )

        return GraphDeduplicationResult(
            deduplicated_graph=graph,
            merges_applied=merges_applied,
            flagged_ambiguous_pairs=ambiguous_pairs,
            raw_response=raw_response,
        )

    def _normalize_batch(self, findings_list: list[dict]) -> NormalizationResult:
        """Normalize a single batch of findings."""
        prepared_findings = self._prepare_findings_for_prompt(findings_list)

        # Prepare input for prompt
        input_data = {"findings_from_multiple_reports": prepared_findings}

        prompt = ENTITY_NORMALIZATION_PROMPT.format(
            findings_array=json.dumps(input_data, indent=2)
        )

        response_text = self._call_llm(prompt)

        # Parse JSON from response
        try:
            data = parse_json_from_text(response_text)
        except Exception as e:
            fallback = self._rule_based_normalize(prepared_findings)
            fallback.flagged_contradictions.insert(
                0, {"error": f"JSON parsing failed: {str(e)}"}
            )
            fallback.raw_response = response_text
            return fallback

        # Convert to dataclass objects
        entities = []
        for entity_data in data.get("normalized_entities", []):
            canonical = entity_data.get("canonical_name", "")
            variants = entity_data.get("variants_seen", [])
            canonical = self._postprocess_canonical_name(canonical, variants)
            entities.append(
                NormalizedEntity(
                    canonical_name=canonical,
                    variants_seen=variants,
                    first_documented=entity_data.get("first_documented", ""),
                    timeline=entity_data.get("timeline", []),
                    current_status=entity_data.get("current_status", "unknown"),
                    certainty_evolution=entity_data.get("certainty_evolution", []),
                )
            )

        return NormalizationResult(
            normalized_entities=entities,
            flagged_contradictions=data.get("flagged_contradictions", []),
            raw_response=response_text,
        )

    def _entity_signature(self, entity_id: str, entity: dict[str, Any]) -> str:
        canonical = str(entity.get("canonical_name") or entity_id)
        site = str(entity.get("anatomical_site") or "")
        etype = str(entity.get("entity_type") or "")
        return f"{canonical} {site} {etype}".strip().lower()

    def _organ_bucket(self, entity: dict[str, Any], entity_id: str) -> str:
        text = f"{entity_id} {entity.get('canonical_name', '')} {entity.get('anatomical_site', '')}".lower()
        mapping = {
            "lung": ["lung", "lobe", "pulmonary", "rul", "lul", "rll", "lll"],
            "liver": ["liver", "hepatic"],
            "adrenal": ["adrenal"],
            "lymph_node": ["lymph", "node", "nodal"],
            "brain": ["brain", "cerebral", "cerebell"],
            "bone": ["bone", "osseous", "skeletal"],
        }
        for bucket, needles in mapping.items():
            if any(token in text for token in needles):
                return bucket
        return "other"

    def _event_overlap_score(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        events_a = a.get("events", [])
        events_b = b.get("events", [])
        if not isinstance(events_a, list) or not isinstance(events_b, list):
            return 0.0
        dates_a = {
            str(e.get("date", ""))
            for e in events_a
            if isinstance(e, dict) and str(e.get("date", ""))
        }
        dates_b = {
            str(e.get("date", ""))
            for e in events_b
            if isinstance(e, dict) and str(e.get("date", ""))
        }
        if not dates_a or not dates_b:
            return 0.0
        intersection = len(dates_a.intersection(dates_b))
        union = len(dates_a.union(dates_b))
        return (intersection / union) if union else 0.0

    def _token_majority_merges(
        self, entities: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Week 3 — Token-majority pre-pass merge.

        Merges entity pairs where ≥70% of meaningful content tokens overlap
        AND both entities share the same inferred body region.

        This deterministic pass runs *before* the SequenceMatcher threshold
        and catches cases that fail the 0.88 threshold because of:
          - Report-index suffixes: "low_lung_volumes" vs "low_lung_volumes_r24"
          - Token reordering:      "atelectasis_bibasilar" vs "bibasilar_atelectasis"
          - Minor qualifier diff:  "pleural_thickening_left" vs "pleural_thickening"

        Safety guards (prevent over-merging):
          - Different body regions → skip
          - Different RadLex IDs   → skip (ontology says they're distinct)
          - Negation mismatch      → skip (present vs absent must stay separate)
          - Token set < 2 content tokens on either side → skip (too short/generic)
        """
        _STOP = {
            "finding",
            "the",
            "of",
            "in",
            "a",
            "an",
            "with",
            "for",
            "and",
            "or",
            "is",
            "are",
            "was",
            "were",
            "no",
            "not",
        }
        # Strip report-index suffixes like _r24, _r25, _report_1
        _REPORT_SUFFIX = re.compile(r"[_\s]r\d+$|[_\s]report[_\s]\d+$", re.I)

        merges: list[dict[str, Any]] = []
        ids = sorted(entities.keys())

        for i, id_a in enumerate(ids):
            if id_a not in entities:
                continue
            a = entities[id_a]
            if not isinstance(a, dict):
                continue

            for id_b in ids[i + 1 :]:
                if id_b not in entities:
                    continue
                b = entities[id_b]
                if not isinstance(b, dict):
                    continue

                # Guard 1: different RadLex IDs → ontology says they're distinct
                rid_a = a.get("radlex_id")
                rid_b = b.get("radlex_id")
                if rid_a and rid_b and str(rid_a) != str(rid_b):
                    continue

                # Guard 2: negation mismatch → present vs absent must stay separate
                neg_a = bool(a.get("is_negated", False))
                neg_b = bool(b.get("is_negated", False))
                if neg_a != neg_b:
                    continue

                # Guard 3: different body regions
                region_a = infer_body_region(
                    str(a.get("canonical_name") or id_a),
                    str(a.get("anatomical_site") or ""),
                )
                region_b = infer_body_region(
                    str(b.get("canonical_name") or id_b),
                    str(b.get("anatomical_site") or ""),
                )
                if region_a != "other" and region_b != "other" and region_a != region_b:
                    continue

                # Compute token overlap on clean canonical names
                name_a = _REPORT_SUFFIX.sub(
                    "", str(a.get("canonical_name") or id_a).lower().replace("_", " ")
                )
                name_b = _REPORT_SUFFIX.sub(
                    "", str(b.get("canonical_name") or id_b).lower().replace("_", " ")
                )

                tok_a = set(name_a.split()) - _STOP
                tok_b = set(name_b.split()) - _STOP

                # Guard 4: too short/generic (single meaningful token is ambiguous)
                if len(tok_a) < 2 or len(tok_b) < 2:
                    continue

                shared = len(tok_a & tok_b)
                min_len = min(len(tok_a), len(tok_b))
                max_len = max(len(tok_a), len(tok_b))
                # ≥70% of the shorter set's tokens must be shared (directional)
                if min_len == 0 or (shared / min_len) < 0.70:
                    continue
                # Bidirectional guard: ≥50% of the LONGER entity's tokens must
                # also overlap. This prevents a short anatomy label (e.g. "medial
                # compartment knee") from absorbing a longer finding entity
                # ("joint space narrowing medial compartment knee") just because
                # all anatomy tokens happen to appear in the longer name.
                if max_len > min_len and (shared / max_len) < 0.50:
                    continue

                # All guards passed → deterministic merge
                target_id, source_id = self._pick_merge_direction(id_a, id_b, entities)
                if self._merge_entity_pair(
                    entities,
                    target_id=target_id,
                    source_id=source_id,
                    reason="token_majority",
                ):
                    merges.append(
                        {
                            "target_entity_id": target_id,
                            "source_entity_id": source_id,
                            "reason": "token_majority",
                            "token_overlap": round(shared / min_len, 3),
                        }
                    )

        return merges

    def _candidate_entity_pairs(
        self, entities: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        ids = sorted(entities.keys())
        pairs: list[dict[str, Any]] = []
        for idx, entity_a in enumerate(ids):
            for entity_b in ids[idx + 1 :]:
                a = entities.get(entity_a, {})
                b = entities.get(entity_b, {})
                if not isinstance(a, dict) or not isinstance(b, dict):
                    continue

                # Already handled deterministically in FactStore for shared RadLex IDs.
                if (
                    a.get("radlex_id")
                    and b.get("radlex_id")
                    and a.get("radlex_id") == b.get("radlex_id")
                ):
                    continue

                # Phase 7 — Body region guard: never merge entities from different body regions.
                region_a = infer_body_region(
                    str(a.get("canonical_name") or entity_a),
                    str(a.get("anatomical_site") or ""),
                )
                region_b = infer_body_region(
                    str(b.get("canonical_name") or entity_b),
                    str(b.get("anatomical_site") or ""),
                )
                if region_a != "other" and region_b != "other" and region_a != region_b:
                    continue

                sig_a = self._entity_signature(entity_a, a)
                sig_b = self._entity_signature(entity_b, b)
                if not sig_a or not sig_b:
                    continue
                score = SequenceMatcher(None, sig_a, sig_b).ratio()

                # Small bonus when first documented dates overlap or are close.
                first_a = str(a.get("first_documented", ""))
                first_b = str(b.get("first_documented", ""))
                if first_a and first_b and first_a[:7] == first_b[:7]:
                    score = min(1.0, score + 0.03)

                # Encourage merge checks when one canonical is strict substring of another.
                canon_a = str(a.get("canonical_name") or entity_a).lower()
                canon_b = str(b.get("canonical_name") or entity_b).lower()
                if canon_a in canon_b or canon_b in canon_a:
                    score = min(1.0, score + 0.08)

                # Same organ bucket should be easier to merge; different buckets should be penalized.
                organ_a = self._organ_bucket(a, entity_a)
                organ_b = self._organ_bucket(b, entity_b)
                if organ_a == organ_b:
                    score = min(1.0, score + 0.06)
                elif organ_a != "other" and organ_b != "other":
                    score = max(0.0, score - 0.12)

                # Ontology-aware confidence boosts/penalties.
                if a.get("snomed_id") and b.get("snomed_id"):
                    if str(a.get("snomed_id")) == str(b.get("snomed_id")):
                        score = min(1.0, score + 0.12)
                    else:
                        score = max(0.0, score - 0.08)
                if (
                    a.get("radlex_id")
                    and b.get("radlex_id")
                    and str(a.get("radlex_id")) != str(b.get("radlex_id"))
                ):
                    score = max(0.0, score - 0.08)

                # Shared-token-majority boost: if ≥75% of content tokens
                # overlap (ignoring stop words), boost score significantly.
                # This catches pairs like "low_lung_volumes" vs "lung_volumes_low".
                _STOP = {"finding", "the", "of", "in", "a", "an", "with", "for"}
                tokens_a = set(canon_a.replace("_", " ").split()) - _STOP
                tokens_b = set(canon_b.replace("_", " ").split()) - _STOP
                if tokens_a and tokens_b:
                    shared = len(tokens_a & tokens_b)
                    min_len = min(len(tokens_a), len(tokens_b))
                    if min_len > 0 and (shared / min_len) >= 0.75:
                        score = min(1.0, score + 0.10)

                overlap = self._event_overlap_score(a, b)
                score = min(1.0, score + (0.05 * overlap))

                pairs.append(
                    {
                        "entity_a": entity_a,
                        "entity_b": entity_b,
                        "similarity_score": round(score, 4),
                        "signature_a": sig_a,
                        "signature_b": sig_b,
                    }
                )
        pairs.sort(key=lambda item: item["similarity_score"], reverse=True)
        return pairs

    def _pick_merge_direction(
        self,
        entity_a: str,
        entity_b: str,
        entities: dict[str, dict[str, Any]],
    ) -> tuple[str, str]:
        a = entities.get(entity_a, {})
        b = entities.get(entity_b, {})
        events_a = len(a.get("events", [])) if isinstance(a.get("events"), list) else 0
        events_b = len(b.get("events", [])) if isinstance(b.get("events"), list) else 0
        if events_a > events_b:
            return entity_a, entity_b
        if events_b > events_a:
            return entity_b, entity_a
        return (entity_a, entity_b) if entity_a <= entity_b else (entity_b, entity_a)

    def _merge_entity_pair(
        self,
        entities: dict[str, dict[str, Any]],
        target_id: str,
        source_id: str,
        reason: str,
    ) -> bool:
        if target_id == source_id:
            return False
        if target_id not in entities or source_id not in entities:
            return False

        target = entities[target_id]
        source = entities[source_id]
        if not isinstance(target, dict) or not isinstance(source, dict):
            return False

        target_events = target.get("events", [])
        source_events = source.get("events", [])
        if not isinstance(target_events, list):
            target_events = []
        if not isinstance(source_events, list):
            source_events = []

        existing_event_ids = {
            str(e.get("event_id", "")) for e in target_events if isinstance(e, dict)
        }
        for event in source_events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id", ""))
            event["entity_id"] = target_id
            if event_id and event_id in existing_event_ids:
                continue
            target_events.append(event)
            if event_id:
                existing_event_ids.add(event_id)
        target["events"] = sorted(
            target_events,
            key=lambda item: (str(item.get("date", "")), str(item.get("event_id", ""))),
        )

        target_traj = target.get("certainty_trajectory", [])
        source_traj = source.get("certainty_trajectory", [])
        if not isinstance(target_traj, list):
            target_traj = []
        if not isinstance(source_traj, list):
            source_traj = []
        seen_traj = {
            (
                str(p.get("date", "")),
                str(p.get("certainty_label", p.get("certainty_level", ""))),
            )
            for p in target_traj
            if isinstance(p, dict)
        }
        for point in source_traj:
            if not isinstance(point, dict):
                continue
            key = (
                str(point.get("date", "")),
                str(point.get("certainty_label", point.get("certainty_level", ""))),
            )
            if key in seen_traj:
                continue
            target_traj.append(point)
            seen_traj.add(key)
        target["certainty_trajectory"] = sorted(
            target_traj,
            key=lambda item: str(item.get("date", "")),
        )

        for field in ["radlex_id", "snomed_id", "anatomical_site"]:
            if not target.get(field) and source.get(field):
                target[field] = source.get(field)

        target_first = str(target.get("first_documented", "")).strip()
        source_first = str(source.get("first_documented", "")).strip()
        if source_first and (not target_first or source_first < target_first):
            target["first_documented"] = source_first

        target_last = str(target.get("last_documented", "")).strip()
        source_last = str(source.get("last_documented", "")).strip()
        if source_last and (not target_last or source_last > target_last):
            target["last_documented"] = source_last

        status_order = {"active": 2, "uncertain": 1, "resolved": 0}
        target_status = str(target.get("status", "active"))
        source_status = str(source.get("status", "active"))
        target["status"] = (
            target_status
            if status_order.get(target_status, 1) >= status_order.get(source_status, 1)
            else source_status
        )

        merge_meta = target.setdefault("merge_metadata", [])
        if isinstance(merge_meta, list):
            merge_meta.append(
                {
                    "source_entity_id": source_id,
                    "reason": reason,
                }
            )

        del entities[source_id]
        return True

    def _resolve_ambiguous_pairs_llm(
        self,
        ambiguous_pairs: list[dict[str, Any]],
        entities: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        shortlist = ambiguous_pairs[:AMBIGUOUS_BATCH_LIMIT]
        payload_pairs = []
        for pair in shortlist:
            a = pair["entity_a"]
            b = pair["entity_b"]
            payload_pairs.append(
                {
                    "entity_a": a,
                    "entity_b": b,
                    "similarity_score": pair["similarity_score"],
                    "a": {
                        "canonical_name": entities.get(a, {}).get("canonical_name"),
                        "entity_type": entities.get(a, {}).get("entity_type"),
                        "anatomical_site": entities.get(a, {}).get("anatomical_site"),
                        "radlex_id": entities.get(a, {}).get("radlex_id"),
                        "event_count": len(entities.get(a, {}).get("events", [])),
                    },
                    "b": {
                        "canonical_name": entities.get(b, {}).get("canonical_name"),
                        "entity_type": entities.get(b, {}).get("entity_type"),
                        "anatomical_site": entities.get(b, {}).get("anatomical_site"),
                        "radlex_id": entities.get(b, {}).get("radlex_id"),
                        "event_count": len(entities.get(b, {}).get("events", [])),
                    },
                }
            )

        prompt = (
            "You are resolving duplicate oncology entities in a Fact Graph.\n"
            "For each pair, decide if they represent the same clinical entity.\n"
            "Return only JSON with schema:\n"
            "{"
            '"merges": ['
            '{"source_entity_id": "...", "target_entity_id": "...", "confidence": 0.0, "reason": "..."}'
            "]"
            "}\n"
            "Rules: only merge when clearly same entity/site; never merge contradictory organs; confidence <= 1.\n"
            f"Pairs:\n{json.dumps(payload_pairs, indent=2)}"
        )

        try:
            response_text = self._call_llm(prompt)
            parsed = parse_json_from_text(response_text)
            merges = parsed.get("merges", []) if isinstance(parsed, dict) else []
            if not isinstance(merges, list):
                merges = []
            return merges, response_text
        except Exception as exc:
            return [], f"llm_dedup_error: {type(exc).__name__}: {exc}"

    def _prepare_findings_for_prompt(self, findings_list: list[dict]) -> list[dict]:
        """
        Normalize incoming shapes to a per-report object list:
        [{"report_date": "...", "findings": [...]}, ...]
        """
        if not findings_list:
            return []

        if isinstance(findings_list[0], dict) and "findings" in findings_list[0]:
            # Already per-report payload.
            normalized = []
            for row in findings_list:
                normalized.append(
                    {
                        "report_date": str(row.get("report_date", "")),
                        "hadm_id": str(row.get("hadm_id", "")),
                        "findings": row.get("findings", []),
                    }
                )
            return normalized

        # Backward compatibility: list of finding arrays.
        normalized = []
        for idx, row in enumerate(findings_list):
            if isinstance(row, list):
                normalized.append(
                    {
                        "report_date": f"report_{idx + 1}",
                        "hadm_id": "",
                        "findings": row,
                    }
                )
        return normalized

    def _canonicalize_entity(self, finding: dict) -> str:
        entity = str(finding.get("entity", "")).lower()
        location = str(finding.get("anatomical_location", "")).lower()
        finding_type = str(finding.get("finding_type", "")).lower()
        joined = " ".join([entity, location, finding_type])

        neoplastic_cues = any(
            token in joined
            for token in (
                "mass",
                "lesion",
                "nodule",
                "tumor",
                "neoplasm",
                "malignan",
                "cancer",
                "carcinoid",
                "metasta",
                "adenopathy",
            )
        )

        if "osseous abnormality" in joined or "bone abnormality" in joined:
            return "finding_osseous_abnormality"

        if "hepatic" in joined or "liver" in joined:
            return "metastasis_liver"
        if "adrenal" in joined and "left" in joined:
            return "metastasis_adrenal_left"
        if "adrenal" in joined and "right" in joined:
            return "metastasis_adrenal_right"
        if (
            "lung" in joined or "lobe" in joined or "pulmonary" in joined
        ) and neoplastic_cues:
            if "right upper" in joined or "rul" in joined:
                return "primary_lung_right_upper_lobe"
            if "right lower" in joined or "rll" in joined:
                return "primary_lung_right_lower_lobe"
            if "left upper" in joined or "lul" in joined:
                return "primary_lung_left_upper_lobe"
            if "left lower" in joined or "lll" in joined:
                return "primary_lung_left_lower_lobe"
            return "primary_lung_unspecified"
        if ("lymph" in joined or "node" in joined) and neoplastic_cues:
            return "lymph_node_unspecified"
        if ("brain" in joined or "cerebell" in joined) and neoplastic_cues:
            return "lesion_brain_unspecified"

        slug = re.sub(r"[^a-z0-9]+", "_", entity.strip().lower()).strip("_")
        if not slug:
            slug = "unspecified_entity"
        return f"finding_{slug}"

    def _finding_measurement_str(self, finding: dict) -> str:
        measurement = finding.get("measurement", {})
        if isinstance(measurement, dict):
            current = str(measurement.get("current", "")).strip()
            trend = str(measurement.get("trend", "")).strip()
            if current and trend:
                return f"{current} ({trend})"
            if current:
                return current
            if trend:
                return trend
        return ""

    def _rule_based_normalize(self, findings_list: list[dict]) -> NormalizationResult:
        """
        Deterministic fallback when LLM normalization fails.
        Ensures non-empty normalized_entities for downstream quality reporting.
        """
        entities: dict[str, NormalizedEntity] = {}
        contradictions: list[dict] = []

        for report in findings_list:
            report_date = str(report.get("report_date", ""))
            report_findings = report.get("findings", [])
            if not isinstance(report_findings, list):
                continue

            for finding in report_findings:
                if not isinstance(finding, dict):
                    continue
                canonical_name = self._canonicalize_entity(finding)
                variant = str(finding.get("entity", "")).strip() or canonical_name
                certainty = str(finding.get("certainty", "")).strip() or "unknown"
                temporal = str(finding.get("temporal_qualifier", "")).strip()
                measurement_str = self._finding_measurement_str(finding)

                if canonical_name not in entities:
                    entities[canonical_name] = NormalizedEntity(
                        canonical_name=canonical_name,
                        variants_seen=[variant],
                        first_documented=report_date or "",
                        timeline=[],
                        current_status=temporal or "observed",
                        certainty_evolution=[],
                    )
                entity = entities[canonical_name]

                if variant not in entity.variants_seen:
                    entity.variants_seen.append(variant)

                timeline_item = {
                    "date": report_date or "",
                    "measurement": measurement_str,
                    "source": "fallback_normalizer",
                }
                entity.timeline.append(timeline_item)
                entity.certainty_evolution.append(
                    {
                        "date": report_date or "",
                        "certainty_level": certainty,
                    }
                )

                if temporal:
                    entity.current_status = temporal

                # Lightweight contradiction flag for conflicting trends.
                if isinstance(finding.get("measurement"), dict):
                    trend = str(finding["measurement"].get("trend", "")).lower()
                    if trend in {
                        "increased",
                        "decreased",
                        "stable",
                    } and entity.current_status not in {"observed", temporal, trend}:
                        contradictions.append(
                            {
                                "entity": canonical_name,
                                "contradiction": f"status trend conflict: {entity.current_status} vs {trend}",
                                "conflicting_reports": [report_date],
                            }
                        )

        merged = self._merge_entities(list(entities.values()))
        return NormalizationResult(
            normalized_entities=merged,
            flagged_contradictions=contradictions,
            raw_response="",
        )

    def _merge_entities(
        self, entities: list[NormalizedEntity]
    ) -> list[NormalizedEntity]:
        """Merge entities with the same canonical_name across batches."""
        merged = {}
        for entity in entities:
            name = entity.canonical_name
            if name in merged:
                existing = merged[name]
                # Merge variants
                for v in entity.variants_seen:
                    if v not in existing.variants_seen:
                        existing.variants_seen.append(v)
                # Merge timelines
                existing.timeline.extend(entity.timeline)
                # Merge certainty evolution
                existing.certainty_evolution.extend(entity.certainty_evolution)
                # Update status to latest
                existing.current_status = entity.current_status
            else:
                merged[name] = entity

        # Deduplicate timeline and certainty evolution entries
        for entity in merged.values():
            seen_timeline = set()
            deduped_timeline = []
            for item in entity.timeline:
                key = (
                    str(item.get("date", "")),
                    str(item.get("measurement", "")),
                    str(item.get("source", "")),
                )
                if key in seen_timeline:
                    continue
                seen_timeline.add(key)
                deduped_timeline.append(item)
            entity.timeline = deduped_timeline

            seen_certainty = set()
            deduped_certainty = []
            for item in entity.certainty_evolution:
                key = (
                    str(item.get("date", "")),
                    str(item.get("certainty_level", "")),
                )
                if key in seen_certainty:
                    continue
                seen_certainty.add(key)
                deduped_certainty.append(item)
            entity.certainty_evolution = deduped_certainty

        return list(merged.values())

    def _postprocess_canonical_name(
        self, canonical_name: str, variants_seen: list[str]
    ) -> str:
        """
        Post-processing guard: if canonical_name is a bare anatomy slug with no
        finding qualifier, attempt to enrich it from variants_seen evidence.

        This catches cases where the LLM normalization produces pure anatomy
        labels like 'finding_paranasal_sinuses' or 'finding_right_hemidiaphragm'
        instead of the clinical finding.
        """
        name = canonical_name.lower().strip()

        # Known anatomy-only patterns → canonical finding label
        ANATOMY_TO_FINDING = {
            # pattern_substr: (canonical_finding, condition: if qualifier in variants)
            "paranasal_sinuses": "finding_paranasal_sinuses_normally_aerated",
            "mastoid_air_cell": "finding_mastoid_air_cells_normally_aerated",
            "right_hemidiaphragm": "finding_right_hemidiaphragm_elevation",
            "left_hemidiaphragm": "finding_left_hemidiaphragm_elevation",
            "craniocervical_junction": "finding_craniocervical_junction_normal",
            "suprasellar_region_abnormality": "finding_suprasellar_region_normal",
        }
        for anatomy_key, corrected in ANATOMY_TO_FINDING.items():
            if name == f"finding_{anatomy_key}" or name == anatomy_key:
                return corrected

        # If canonical is 'finding_territorial' (partial adjective, not a finding)
        # and variants contain infarct language, rename to canonical form
        if name == "finding_territorial":
            combined_variants = " ".join(str(v).lower() for v in variants_seen)
            if "infarct" in combined_variants or "ischemia" in combined_variants:
                return "finding_vascular_territorial_infarct"

        return canonical_name

    def _call_llm(self, prompt: str) -> str:
        """Call Azure OpenAI with the given prompt."""
        return self.llm_client.chat(prompt, max_tokens=4000, temperature=0.0)
