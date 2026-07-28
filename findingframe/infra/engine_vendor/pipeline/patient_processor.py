"""
Patient Processor: v2-oriented end-to-end pipeline for cancer patient timelines.

Pipeline order:
1. Finding extraction (Agent 1)
2. Ontology grounding (new)
3. Append-only Fact Graph write (new)
4. GC render from Fact Graph (Agent 3 refactor)
5. Structured progression analysis from Fact Graph (Agent 4 upgrade path)
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

import pandas as pd
from tqdm import tqdm

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from clinical_dimensions import ClinicalDimensionAnalyzer
from entity_grounding import EntityGrounder
from extraction import FindingExtractor, HybridExtractor, EntityNormalizer
from extraction.report_cleaner import clean_report
from extraction.canonical_vocabulary import normalize_entity_name
from fact_graph import FactStore
from gc_system import GCUpdater, ProgressionAnalyzer


logger = logging.getLogger("pipeline.patient_processor")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Fix #1 + #2: Cancer entity context validation
# ---------------------------------------------------------------------------

# Body-region tokens that must appear in evidence for each cancer entity type.
# If a cancer entity is created but its evidence text contains NONE of its
# required body tokens, the entity is a VOCAB_OVER_REACH false positive and
# should be rejected.
_CANCER_ENTITY_BODY_TOKENS: dict[str, list[str]] = {
    "hepatic_metastases": ["liver", "hepat", "hepatic"],
    "finding_hepatic_metastases": ["liver", "hepat", "hepatic"],
    "pulmonary_metastases": ["lung", "pulmon", "chest", "nodule"],
    "finding_pulmonary_metastases": ["lung", "pulmon", "chest", "nodule"],
    "bone_metastases": ["bone", "osseous", "skeletal", "lytic", "sclerotic", "osteolyt"],
    "finding_bone_metastases": ["bone", "osseous", "skeletal", "lytic", "sclerotic"],
    "brain_metastases": ["brain", "intracranial", "cerebral", "cerebell"],
    "finding_brain_metastases": ["brain", "intracranial", "cerebral"],
    "lung_cancer": ["lung", "pulmon", "chest", "bronchogenic", "carcinoma"],
    "breast_cancer": ["breast", "mammo", "mammary", "ductal"],
    "colon_cancer": ["colon", "colorectal", "rectal", "bowel"],
    "brain_tumor": ["brain", "glioma", "intracranial", "cerebral", "frontal", "temporal", "parietal", "occipital"],
    "adrenal_metastases": ["adrenal"],
    "finding_adrenal_metastases": ["adrenal"],
    "adrenal_metastasis_left": ["adrenal"],
    "finding_lymph_node_metastases": ["lymph", "nodal", "node", "adenopathy"],
    "finding_peritoneal_metastases": ["peritoneal", "oment", "mesenter"],
}


def _reject_cancer_entity_context_mismatch(
    canonical_name: str, finding: dict[str, Any]
) -> bool:
    """Return True if this cancer entity should be REJECTED.

    Checks whether the evidence text contains body-region-specific tokens
    that match the entity type.  If the vocabulary created a cancer entity
    but the evidence comes from an unrelated body region or context, the
    entity is a false positive.
    """
    required_tokens = _CANCER_ENTITY_BODY_TOKENS.get(canonical_name)
    if not required_tokens:
        return False  # not a cancer entity subject to gating

    evidence = _safe_str(
        finding.get("evidence_text") or finding.get("negation_language") or ""
    ).strip().lower()

    anatomical_site = _safe_str(
        finding.get("anatomical_location") or ""
    ).strip().lower()

    combined = f"{evidence} {anatomical_site}"

    # Any body-region token present → keep the entity
    if any(token in combined for token in required_tokens):
        return False

    return True  # reject — no body match


def _extract_sentence_containing_span(
    report_text: str, span_start: int, span_end: int
) -> str:
    """Extract the full sentence that contains the given character span."""
    if span_start < 0 or span_end <= span_start or span_end > len(report_text):
        return ""
    # Find sentence start — look backwards for period, newline, or start
    start = max(
        report_text.rfind(". ", 0, span_start),
        report_text.rfind("\n", 0, span_start),
        0,
    )
    if start > 0:
        start += 2 if report_text[start:start+2] == ". " else 1 if report_text[start] == "\n" else 0
    # Find sentence end
    end = report_text.find(". ", span_end)
    if end == -1:
        end = report_text.find("\n", span_end)
    if end == -1:
        end = len(report_text)
    else:
        end += 1  # include the period
    return report_text[start:end].strip()


def validate_paired_finding_in_current_report(
    finding: dict[str, Any],
    current_report_text: str,
) -> bool:
    """
    Return True if the finding is supported by the CURRENT report text.

    Rejects findings whose evidence appears only in the previous-report
    context (context bleed) or whose evidence cannot be located at all.

    Constraints enforced (from M4 decision gate):
    1. evidence_text must be locatable in the current report
    2. entity name tokens must appear in the current report
    3. do not promote previous-report-only findings
    """
    if not isinstance(finding, dict):
        return False

    entity_name = _safe_str(
        finding.get("entity") or finding.get("finding") or ""
    ).strip()
    evidence_text = _safe_str(
        finding.get("evidence_text") or finding.get("negation_language") or ""
    ).strip()

    if not entity_name:
        return False

    curr_text_lower = current_report_text.lower()
    evidence_lower = evidence_text.lower()
    entity_lower = entity_name.lower()

    # Constraint 1: evidence_text must be locatable as a substring in
    # the current report.  A lenient minimum-tokens check is used
    # instead of a rigid full-substring match because the LLM may
    # slightly paraphrase the sentence from the report.
    evidence_tokens = [
        t for t in re.findall(r"\b[a-z]{4,}\b", evidence_lower)
    ]
    if evidence_tokens:
        matched = sum(
            1 for t in evidence_tokens if t in curr_text_lower
        )
        match_ratio = matched / len(evidence_tokens)
        if match_ratio < 0.5:
            return False  # evidence not anchorable in current report

    # Constraint 2: at least one significant entity-name token must
    # appear in the current report text.
    entity_tokens = [
        t for t in re.findall(r"\b[a-z]{3,}\b", entity_lower)
        if t not in {"the", "and", "for", "are", "not", "was", "has", "had",
                      "with", "this", "that", "from", "have", "been", "will",
                      "finding", "abnormality", "evidence", "normal"}
    ]
    if entity_tokens:
        matched = sum(
            1 for t in entity_tokens if t in curr_text_lower
        )
        if matched == 0:
            return False  # entity absent from current report

    return True


class PatientProcessor:
    """
    End-to-end processor for cancer patient timelines.
    Uses the configured LLM provider through existing agent clients where needed.
    """

    # G2: class-level defaults so PatientProcessor.__new__() callers that do not
    # set these attributes explicitly still get the correct "all on" behaviour.
    use_radlex_merge: bool = True
    use_normalizer: bool = True

    # M4B: paired-mode constraint counters for diagnostic visibility
    paired_context_bleed_dropped: int = 0
    paired_no_evidence_dropped: int = 0

    def __init__(
        self,
        output_dir: str = "./outputs/patient_gcs",
        save_intermediate: bool = True,
        use_hybrid_extraction: bool = True,
        use_vector_grounding: bool = True,
        use_scispacy: bool = True,
        use_paired_extraction: bool = False,
        use_radlex_merge: bool = True,
        use_normalizer: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.save_intermediate = save_intermediate
        self.use_paired_extraction = use_paired_extraction
        # G2: ablation toggles — control individual subsystem activation
        self.use_radlex_merge = use_radlex_merge
        self.use_normalizer = use_normalizer

        print("Initializing agents...")
        if use_hybrid_extraction:
            self.extractor = HybridExtractor()
        else:
            self.extractor = FindingExtractor()
        self.entity_grounder = EntityGrounder(
            use_vector_grounding=use_vector_grounding,
            use_scispacy=use_scispacy,
        )
        self.normalizer = EntityNormalizer()
        self.clinical_dimension_analyzer = ClinicalDimensionAnalyzer()
        self.gc_updater = GCUpdater()
        self.progression_analyzer = ProgressionAnalyzer()
        # Build RadLex parent hierarchy for cross-report merge
        self._radlex_hierarchy = self._build_radlex_hierarchy()
        print("Agents initialized!")

    def _build_radlex_hierarchy(self) -> dict[str, list[str]]:
        """Build RID → parent RIDs mapping from the EntityGrounder's RadLex loader."""
        hierarchy: dict[str, list[str]] = {}
        try:
            loader = self.entity_grounder.radlex
            if not loader._loaded:
                loader.load()
            for concept in loader._concepts:
                if concept.concept_id and concept.parents:
                    hierarchy[concept.concept_id] = list(concept.parents)
        except Exception as e:
            print(f"  Warning: could not build RadLex hierarchy: {e}")
        return hierarchy

    def _safe_report_id(self, report: pd.Series, index: int) -> str:
        # Always use sequential index for consistent report numbering.
        # This ensures gold annotation report indices (1, 2, ...) map directly
        # to fact graph source_report_id values (report_1, report_2, ...).
        return f"report_{index}"

    def _normalized_entities_from_fact_graph(
        self, fact_graph: dict[str, Any]
    ) -> list[dict[str, Any]]:
        entities = fact_graph.get("entities", {})
        if not isinstance(entities, dict):
            return []
        normalized_entities: list[dict[str, Any]] = []
        for entity_id, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            timeline = []
            events = entity.get("events", [])
            if isinstance(events, list):
                for event in sorted(
                    events,
                    key=lambda e: (str(e.get("date", "")), str(e.get("event_id", ""))),
                ):
                    measurement = (
                        event.get("measurement", {}) if isinstance(event, dict) else {}
                    )
                    measurement_text = ""
                    if isinstance(measurement, dict):
                        if measurement.get("normalized_mm") is not None:
                            measurement_text = f"{measurement.get('normalized_mm')} mm"
                        elif measurement.get("raw_text"):
                            measurement_text = str(measurement.get("raw_text"))
                    timeline.append(
                        {
                            "date": str(event.get("date", "")),
                            "measurement": measurement_text,
                            "source": str(event.get("source_report_id", "")),
                            "modality": str(event.get("modality", "OTHER")),
                        }
                    )
            normalized_entities.append(
                {
                    "canonical_name": entity_id,
                    "variants_seen": [entity.get("canonical_name", entity_id)],
                    "first_documented": str(entity.get("first_documented", "")),
                    "timeline": timeline,
                    "current_status": str(entity.get("status", "unknown")),
                    "certainty_evolution": entity.get("certainty_trajectory", []),
                    "radlex_id": entity.get("radlex_id"),
                    "snomed_id": entity.get("snomed_id"),
                }
            )
        return normalized_entities

    def _normalize_significant_negative(
        self, negative: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not isinstance(negative, dict):
            return None
        entity = str(
            negative.get("entity")
            or negative.get("finding")
            or negative.get("finding_type")
            or negative.get("anatomical_location")
            or ""
        ).strip()
        if not entity:
            return None

        negation_language = str(
            negative.get("negation_language")
            or negative.get("evidence_text")
            or "negated finding"
        ).strip()
        # G5: preserve the full evidence_text from the original extraction so
        # that span recovery in FactStore.append_grounded_finding() can locate
        # the entity tokens in the source sentence.
        evidence_text = str(
            negative.get("evidence_text")
            or negative.get("negation_language")
            or negation_language
        ).strip()
        try:
            confidence_score = float(negative.get("confidence_score", 0.95) or 0.95)
        except Exception:
            confidence_score = 0.95
        return {
            "entity": entity,
            "anatomical_location": negative.get("anatomical_location"),
            "finding_type": str(negative.get("finding_type") or "negative_finding"),
            "measurement": {"current": negation_language},
            "certainty": str(negative.get("certainty") or "confirmed"),
            "confidence_score": confidence_score,
            "temporal_qualifier": negative.get("temporal_qualifier"),
            "comparison_to_prior": negative.get("comparison_to_prior"),
            "is_negated": True,
            "negation_language": negation_language,
            # G5: evidence_text required by span recovery in append_grounded_finding()
            # For negated findings, the negation_language phrase IS the evidence sentence.
            "evidence_text": evidence_text,
        }

    # Keywords that make a negated finding clinically relevant regardless of indication.
    # A negated finding containing any of these is ALWAYS kept because ruling out
    # these conditions is itself clinically informative.
    _CRITICAL_NEGATED_KEYWORDS = frozenset(
        {
            # Oncologic
            "metastasis",
            "metastases",
            "metastatic",
            "tumor",
            "tumour",
            "carcinoma",
            "malignancy",
            "malignant",
            "cancer",
            "neoplasm",
            "neoplastic",
            "lesion",
            "mass",
            "lymphadenopathy",
            "recurrence",
            "progression",
            # Vascular/hemorrhagic
            "hemorrhage",
            "haemorrhage",
            "thrombosis",
            "embolism",
            "infarct",
            "infarction",
            # Trauma/structural
            "pneumothorax",
            "fracture",
            "dislocation",
            # Neurological
            "hydrocephalus",
            "midline",
            "shift",
            "herniation",
            "enhancement",
            # Effusion/fluid
            "effusion",
            # Obstruction
            "obstruction",
            # Abnormality (generic — if the report explicitly names an abnormality
            # as absent, it's answering a clinical question)
            "abnormality",
        }
    )

    def _apply_negation_policy_filter(
        self,
        findings: list[dict[str, Any]],
        indication: str,
    ) -> list[dict[str, Any]]:
        """
        Drop negated findings that are routine normals unrelated to the
        study's clinical indication.

        Policy (from annotation guidelines):
          - Keep ALL non-negated (positive) findings
          - Keep negated findings that answer the clinical question
            (entity tokens overlap with indication tokens)
          - Keep negated findings containing oncologic/critical keywords
          - Drop everything else (routine negated normals like
            "no appendicitis" in a knee XR)
        """
        if not findings:
            return findings

        # If no indication is available we cannot judge relevance,
        # so keep everything rather than risk dropping real findings.
        if not indication or not indication.strip():
            return findings

        # Tokenize indication for overlap checking
        indication_tokens = (
            set(re.sub(r"[^a-z0-9\s]", " ", indication.lower()).split())
            if indication
            else set()
        )

        kept: list[dict[str, Any]] = []
        dropped = 0

        for finding in findings:
            if not isinstance(finding, dict):
                kept.append(finding)
                continue

            is_negated = bool(finding.get("is_negated", False))

            # Non-negated findings always kept
            if not is_negated:
                kept.append(finding)
                continue

            entity_name = str(
                finding.get("entity") or finding.get("finding") or ""
            ).lower()
            entity_tokens = set(re.sub(r"[^a-z0-9\s]", " ", entity_name).split())

            # Keep if entity contains oncologic/critical keywords
            if entity_tokens & self._CRITICAL_NEGATED_KEYWORDS:
                kept.append(finding)
                continue

            # Keep if entity tokens overlap with indication
            if indication_tokens and (entity_tokens & indication_tokens):
                kept.append(finding)
                continue

            # Drop: routine negated normal unrelated to indication
            dropped += 1

        if dropped > 0:
            logger.info(
                "Negation policy filter dropped %d routine negated findings",
                dropped,
            )

        return kept

    def _consolidate_sub_findings(
        self, findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Merge sub-findings into their parent entity when both appear in the
        same extraction result.

        Example: if both "rib fracture right sixth surgical" and
        "incomplete periosteal bridging" appear, and the latter's tokens are
        a proper subset of the former's, merge them (keep the parent, append
        the child's evidence to the parent's evidence_text).
        """
        if len(findings) < 2:
            return findings

        def _content_tokens(name: str) -> set[str]:
            return set(re.sub(r"[^a-z0-9\s]", " ", name.lower()).split()) - {
                "finding",
                "no",
                "the",
                "of",
                "in",
                "a",
                "an",
                "is",
                "are",
            }

        # Build token sets for each finding
        indexed = []
        for i, f in enumerate(findings):
            name = str(f.get("entity") or f.get("finding") or "")
            tokens = _content_tokens(name)
            indexed.append((i, f, tokens))

        absorbed: set[int] = set()

        for i, f_i, tokens_i in indexed:
            if i in absorbed or len(tokens_i) < 2:
                continue
            for j, f_j, tokens_j in indexed:
                if j <= i or j in absorbed or len(tokens_j) < 2:
                    continue
                # Check if one is a proper subset of the other
                if tokens_j < tokens_i:
                    # j is a sub-finding of i — absorb j into i
                    child_evidence = str(
                        f_j.get("evidence_text") or f_j.get("entity") or ""
                    )
                    parent_evidence = str(f_i.get("evidence_text") or "")
                    if child_evidence and child_evidence not in parent_evidence:
                        f_i["evidence_text"] = (
                            f"{parent_evidence}; {child_evidence}"
                            if parent_evidence
                            else child_evidence
                        )
                    absorbed.add(j)
                elif tokens_i < tokens_j:
                    # i is a sub-finding of j — absorb i into j
                    child_evidence = str(
                        f_i.get("evidence_text") or f_i.get("entity") or ""
                    )
                    parent_evidence = str(f_j.get("evidence_text") or "")
                    if child_evidence and child_evidence not in parent_evidence:
                        f_j["evidence_text"] = (
                            f"{parent_evidence}; {child_evidence}"
                            if parent_evidence
                            else child_evidence
                        )
                    absorbed.add(i)
                    break  # i was absorbed, stop checking it

        if absorbed:
            logger.info(
                "Sub-finding consolidation merged %d findings into parents",
                len(absorbed),
            )

        return [f for idx, f, _ in indexed if idx not in absorbed]

    def _dedupe_findings(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, bool, str]] = set()
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            key = (
                str(
                    finding.get("entity")
                    or finding.get("entity_name")
                    or finding.get("finding")
                    or ""
                )
                .strip()
                .lower(),
                str(finding.get("anatomical_location") or "").strip().lower(),
                bool(finding.get("is_negated", False)),
                str(finding.get("negation_language") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped

    # ------------------------------------------------------------------
    # M4B: Paired-mode post-extraction constraint validation
    # ------------------------------------------------------------------

    def _validate_paired_finding_in_current_report(
        self,
        finding: dict[str, Any],
        current_report_text: str,
    ) -> bool:
        """Delegate to module-level validator."""
        return validate_paired_finding_in_current_report(
            finding, current_report_text
        )

    def _filter_paired_context_bleed(
        self,
        findings: list[dict[str, Any]],
        current_report_text: str,
        report_id: str,
    ) -> list[dict[str, Any]]:
        """Filter out paired-mode findings that are context bleed."""
        kept: list[dict[str, Any]] = []
        dropped = 0
        no_evidence = 0
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            if validate_paired_finding_in_current_report(
                finding, current_report_text
            ):
                kept.append(finding)
            else:
                dropped += 1
                entity_name = _safe_str(
                    finding.get("entity") or finding.get("finding") or "?"
                )
                evidence_text = _safe_str(
                    finding.get("evidence_text") or finding.get("negation_language") or "?"
                )
                if not evidence_text.strip():
                    no_evidence += 1
                logger.info(
                    "paired context-bleed dropped: entity=%s evidence=%s report=%s",
                    entity_name,
                    evidence_text[:80],
                    report_id,
                )

        self.paired_context_bleed_dropped += dropped
        self.paired_no_evidence_dropped += no_evidence
        if dropped > 0:
            logger.info(
                "paired constraint filter: dropped %d/%d findings from %s",
                dropped,
                dropped + len(kept),
                report_id,
            )
        return kept

    def _surface_form_for_grounding(self, finding: dict[str, Any]) -> str:
        surface_form = str(
            finding.get("entity")
            or finding.get("anatomical_location")
            or finding.get("finding_type")
            or "unspecified finding"
        ).strip()
        evidence_text = str(
            finding.get("evidence_text") or finding.get("negation_language") or ""
        ).strip()
        # For bare/ambiguous entity names (bone, abnormal, etc.), enrich with
        # the evidence/negation text so the grounder has context for canonical naming.
        _AMBIGUOUS_ENTITY_NAMES = {
            "bone",
            "osseous",
            "skeletal",
            "abnormal",
            "abnormality",
        }
        if surface_form.lower() not in _AMBIGUOUS_ENTITY_NAMES or not evidence_text:
            return surface_form

        cleaned = evidence_text
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
        ).strip(" .")
        return cleaned or surface_form

    def process_patient(
        self,
        subject_id: str,
        reports_df: pd.DataFrame,
        show_progress: bool = True,
    ) -> dict:
        """
        Process complete timeline for one cancer patient.
        """
        patient_reports = reports_df[
            reports_df["subject_id"] == int(subject_id)
        ].sort_values("charttime")

        if patient_reports.empty:
            return {
                "subject_id": subject_id,
                "error": "No reports found for patient",
                "gc": None,
                "progression": None,
            }

        print(f"\nProcessing patient {subject_id} ({len(patient_reports)} reports)")

        run_start_time = time.time()
        fact_store = FactStore(
            subject_id=subject_id,
            output_dir=str(self.output_dir),
            radlex_hierarchy=self._radlex_hierarchy,
        )
        fact_store.load()
        current_gc = self.gc_updater.initialize_gc(subject_id)
        llm_calls_v2 = 0
        report_errors: list[dict[str, str]] = []
        successful_reports = 0
        raw_report_chunks: list[str] = []  # accumulated for raw_reports.md
        total_findings_extracted = 0

        reports_iter = patient_reports.iterrows()
        if show_progress:
            reports_iter = tqdm(list(reports_iter), desc=f"Patient {subject_id}")

        for sequence_idx, (_, report) in enumerate(reports_iter, start=1):
            report_date = str(report.get("charttime", "Unknown"))
            hadm_id = str(report.get("hadm_id", "Unknown"))
            report_id = self._safe_report_id(report, sequence_idx)
            study_type = str(report.get("note_type", "RR"))
            report_text = str(report.get("text", ""))

            # Accumulate raw report for raw_reports.md used by evaluator.
            note_id = f"{subject_id}-{study_type}-{report_id}"
            raw_report_chunks.append(
                f"## Report {sequence_idx}\n\n"
                f"- **Date:** {report_date}\n"
                f"- **Note ID:** {note_id}\n"
                f"- **Type:** {study_type}\n\n"
                f"### Report Text\n\n{report_text}\n"
            )

            try:
                extraction_result = self.extractor.extract(
                    report_text=report_text,
                    chart_date=report_date,
                    study_type=study_type,
                )
                llm_calls_v2 += 1  # Agent 1 extraction call
            except Exception as e:
                message = (
                    f"Extraction failed for report {report_id}: {type(e).__name__}: {e}"
                )
                print(message)
                report_errors.append(
                    {
                        "report_id": report_id,
                        "report_date": report_date,
                        "error": message,
                    }
                )
                continue

            llm_failure_note = next(
                (
                    str(item)
                    for item in extraction_result.critical_ambiguities
                    if isinstance(item, str)
                    and item.lower().startswith("llm call failed")
                ),
                None,
            )
            if llm_failure_note:
                report_errors.append(
                    {
                        "report_id": report_id,
                        "report_date": report_date,
                        "error": llm_failure_note,
                    }
                )
            else:
                successful_reports += 1

            all_findings: list[dict[str, Any]] = []
            for finding in extraction_result.primary_findings:
                if isinstance(finding, dict):
                    all_findings.append(finding)
            for negative in extraction_result.significant_negatives:
                normalized_negative = self._normalize_significant_negative(negative)
                if normalized_negative:
                    all_findings.append(normalized_negative)
            all_findings = self._dedupe_findings(all_findings)

            # Phase 2A Step 1: Negation policy filter — drop routine negated
            # normals that don't answer the study's clinical question.
            cleaned = clean_report(report_text)
            all_findings = self._apply_negation_policy_filter(
                all_findings, cleaned.indication
            )

            # Phase 2A Step 2: Sub-finding consolidation — merge child
            # findings into their parent when both appear in the same report.
            all_findings = self._consolidate_sub_findings(all_findings)

            newly_added_events: list[dict[str, Any]] = []
            # Fix 3: build oncologic context from the fact graph accumulated so far.
            # If any active, non-negated oncologic entity exists, permit oncologic grounding.
            current_graph = fact_store.serialize()
            report_context = {
                "has_malignancy_history": any(
                    entity.get("entity_type")
                    in ("primary_tumor", "metastasis", "lymph_node_metastasis")
                    or any(
                        term in str(entity.get("canonical_name", "")).lower()
                        for term in ("metast", "tumor", "carcinoma", "malignancy")
                    )
                    for entity in current_graph.get("entities", {}).values()
                    if isinstance(entity, dict)
                    and not entity.get("is_negated", False)
                    and entity.get("status") == "active"
                )
            }
            for finding_idx, finding in enumerate(all_findings, start=1):
                # Fix #3: if evidence is the generic "negated finding" placeholder,
                # clear it so span recovery can try harder.
                if _safe_str(finding.get("evidence_text")).strip() == "negated finding":
                    finding["evidence_text"] = ""

                surface_form = self._surface_form_for_grounding(finding)
                grounded = self.entity_grounder.ground(
                    surface_form=surface_form,
                    report_context=report_context,
                )
                if grounded.grounding_method == "llm_assisted":
                    llm_calls_v2 += 1
                grounded_dict = grounded.to_dict()
                # P2: normalise entity name through canonical vocabulary
                grounded_dict["canonical_name"] = normalize_entity_name(
                    grounded_dict.get("canonical_name", "")
                )
                # Fix #1 + #2: reject cancer entities with wrong-context evidence
                if _reject_cancer_entity_context_mismatch(
                    grounded_dict["canonical_name"], finding
                ):
                    self.paired_context_bleed_dropped += 1
                    continue
                # P5: attach report text so FactStore can recover evidence from spans
                finding["_source_report_text"] = report_text
                event = fact_store.append_grounded_finding(
                    finding=finding,
                    grounded_entity=grounded_dict,
                    report_date=report_date,
                    hadm_id=hadm_id,
                    report_id=report_id,
                    modality=str(
                        finding.get("modality")
                        or extraction_result.report_metadata.get("modality")
                        or "OTHER"
                    ),
                    event_index=finding_idx,
                )
                newly_added_events.append(event.model_dump(mode="json"))

            total_findings_extracted += len(all_findings)

            # Invariant check 1: non-zero findings
            if not all_findings and len(report_text.strip()) > 100:
                logger.warning(
                    "INVARIANT: zero findings extracted",
                    extra={"report_id": report_id, "metric": "zero_findings"},
                )

            # Invariant check 3: entity count per report must not exceed 50
            if len(all_findings) > 50:
                logger.warning(
                    "INVARIANT: entity count exceeds 50 — possible hallucination",
                    extra={
                        "report_id": report_id,
                        "metric": "entity_count_spike",
                        "actual": len(all_findings),
                    },
                )

            # Incremental render after each report, full re-render later after dedupe.
            current_gc = self.gc_updater.render_from_fact_graph(
                fact_store.serialize(),
                mode="incremental",
                current_gc=current_gc,
                new_events=newly_added_events,
            )
            if self.gc_updater.render_mode == "llm":
                llm_calls_v2 += 1

            if self.save_intermediate:
                intermediate_path = (
                    self.output_dir / f"subject_{subject_id}_{report_id}.md"
                )
                with open(intermediate_path, "w", encoding="utf-8") as f:
                    f.write(current_gc)

        # Agent 2 dedupe pass: deterministic by RadLex + ambiguous pair resolution.
        # G2: initialize dedupe_result stub so the analysis payload can always
        # reference dedupe_result.merges_applied / flagged_ambiguous_pairs even
        # when use_normalizer=False.
        from types import SimpleNamespace
        dedupe_result = SimpleNamespace(
            deduplicated_graph=fact_store.serialize(),
            raw_response=None,
            merges_applied=[],
            flagged_ambiguous_pairs=[],
        )
        entities_before_norm = len(fact_store.get_patient_graph().entities)
        if self.use_radlex_merge:
            fact_store.merge_entities_by_radlex()
        if self.use_normalizer:
            dedupe_result = self.normalizer.deduplicate_fact_graph(fact_store.serialize())
            fact_store.replace_graph(dedupe_result.deduplicated_graph)
            if dedupe_result.raw_response and not str(
                dedupe_result.raw_response
            ).startswith("llm_dedup_error"):
                llm_calls_v2 += 1

        # Invariant check 2: normalization drop ≤ 30%
        entities_after_norm = len(fact_store.get_patient_graph().entities)
        if entities_before_norm > 0:
            drop_ratio = 1.0 - (entities_after_norm / entities_before_norm)
            if drop_ratio > 0.30:
                logger.warning(
                    "INVARIANT: normalization drop exceeds 30%%",
                    extra={
                        "subject_id": subject_id,
                        "metric": "normalization_drop",
                        "before": entities_before_norm,
                        "after": entities_after_norm,
                        "drop_pct": round(drop_ratio * 100, 1),
                    },
                )

        # M8 clinical dimensions: uncertainty trajectories + modality awareness.
        enhanced_graph, clinical_dimensions = self.clinical_dimension_analyzer.analyze(
            fact_store.serialize()
        )
        fact_store.replace_graph(enhanced_graph)

        fact_graph_path = fact_store.save()
        current_gc = self.gc_updater.render_from_fact_graph(
            fact_store.serialize(),
            mode="full",
        )
        if self.gc_updater.render_mode == "llm":
            llm_calls_v2 += 1

        progression_result = self.progression_analyzer.analyze_fact_graph(
            fact_store.serialize()
        )
        if progression_result.recist_details.get("non_target_llm_used"):
            llm_calls_v2 += 1

        final_gc_path = self.gc_updater.save_gc(
            gc_content=current_gc,
            subject_id=subject_id,
            output_dir=str(self.output_dir),
            save_history=True,
        )

        normalized_entities = self._normalized_entities_from_fact_graph(
            fact_store.serialize()
        )
        analysis_payload = {
            "subject_id": subject_id,
            "processed_at": datetime.now().isoformat(),
            "num_reports": len(patient_reports),
            "num_reports_successful": successful_reports,
            "num_reports_failed": len(report_errors),
            "report_errors": report_errors,
            "normalized_entities": normalized_entities,
            "contradictions": [],
            "entity_deduplication": {
                "merges_applied": dedupe_result.merges_applied,
                "flagged_ambiguous_pairs": dedupe_result.flagged_ambiguous_pairs,
            },
            "clinical_dimensions": clinical_dimensions,
            "progression": {
                "status": progression_result.disease_status,
                "confidence": progression_result.confidence,
                "evidence": progression_result.key_evidence,
                "summary": progression_result.timeline_summary,
                "significance": progression_result.clinical_significance,
                "recommendations": progression_result.recommendations,
                "recist_details": progression_result.recist_details,
            },
            "fact_graph_path": fact_graph_path,
            "llm_calls_v2": llm_calls_v2,
        }
        # Write raw_reports.md for evaluator / annotator tools.
        raw_reports_md = (
            f"# Raw Radiology Reports — Patient {subject_id}\n\n"
            f"**Total Reports:** {len(raw_report_chunks)}\n\n---\n\n"
            + "\n---\n\n".join(raw_report_chunks)
        )
        raw_reports_path = self.output_dir / f"subject_{subject_id}_raw_reports.md"
        raw_reports_path.write_text(raw_reports_md, encoding="utf-8")

        results_path = self.output_dir / f"subject_{subject_id}_analysis.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(analysis_payload, f, indent=2)

        print(f"Saved GC to: {final_gc_path}")
        print(f"Saved Fact Graph to: {fact_graph_path}")
        print(f"Disease Status: {progression_result.disease_status}")

        # Structured run summary
        run_duration = time.time() - run_start_time
        grounded_count = sum(
            1 for e in fact_store.get_patient_graph().entities.values() if e.radlex_id
        )
        run_summary = {
            "subject_id": subject_id,
            "reports_attempted": len(patient_reports),
            "reports_succeeded": successful_reports,
            "reports_failed": len(report_errors),
            "total_findings_extracted": total_findings_extracted,
            "entities_before_normalization": entities_before_norm,
            "entities_after_normalization": entities_after_norm,
            "entities_with_radlex_id": grounded_count,
            "llm_calls": llm_calls_v2,
            "run_duration_seconds": round(run_duration, 1),
        }
        summary_line = json.dumps(run_summary)
        print(f"\n=== RUN SUMMARY ===\n{summary_line}")
        logger.info("Pipeline run complete", extra=run_summary)

        # Write summary to log file
        summary_path = self.output_dir / f"subject_{subject_id}_run_summary.json"
        summary_path.write_text(json.dumps(run_summary, indent=2), encoding="utf-8")

        return {
            "subject_id": subject_id,
            "gc": current_gc,
            "gc_path": final_gc_path,
            "fact_graph_path": fact_graph_path,
            "fact_graph": fact_store.serialize(),
            "clinical_dimensions": clinical_dimensions,
            "progression": progression_result,
            "normalized_entities": normalized_entities,
            "num_reports_processed": successful_reports,
            "num_reports_failed": len(report_errors),
            "report_errors": report_errors,
        }

    def process_batch(
        self,
        subject_ids: list,
        reports_df: pd.DataFrame,
        max_patients: Optional[int] = None,
    ) -> list[dict]:
        if max_patients:
            subject_ids = subject_ids[:max_patients]

        results = []
        process_fn = (
            self.process_patient_paired
            if self.use_paired_extraction
            else self.process_patient
        )
        mode_label = "paired" if self.use_paired_extraction else "standard"
        for subject_id in tqdm(subject_ids, desc=f"Processing patients ({mode_label})"):
            try:
                result = process_fn(
                    subject_id=str(subject_id),
                    reports_df=reports_df,
                    show_progress=False,
                )
                results.append(result)
            except Exception as e:
                print(f"Error processing {subject_id}: {e}")
                results.append(
                    {
                        "subject_id": subject_id,
                        "error": str(e),
                        "gc": None,
                        "progression": None,
                    }
                )

        return results

    def process_patient_paired(
        self,
        subject_id: str,
        reports_df: pd.DataFrame,
        show_progress: bool = True,
    ) -> dict:
        """
        Process patient timeline with PAIRED REPORT PROCESSING.

        This method processes reports chronologically in consecutive pairs,
        enabling:
        1. Consistent entity naming across reports
        2. Temporal change classification (NEW/UNCHANGED/IMPROVED/WORSENED/RESOLVED)
        3. Better longitudinal entity tracking

        Args:
            subject_id: Patient identifier
            reports_df: DataFrame with all patient reports
            show_progress: Show progress bar

        Returns:
            dict with gc, progression, metrics, and paired_processing=true flag
        """
        from extraction.paired_extractor import PairedFindingExtractor

        patient_reports = reports_df[
            reports_df["subject_id"] == int(subject_id)
        ].sort_values("charttime")

        if patient_reports.empty:
            return {
                "subject_id": subject_id,
                "error": "No reports found for patient",
                "gc": None,
                "progression": None,
                "paired_processing": True,
            }

        print(
            f"\nProcessing patient {subject_id} with PAIRED PROCESSING ({len(patient_reports)} reports)"
        )

        run_start_time = time.time()
        fact_store = FactStore(
            subject_id=subject_id,
            output_dir=str(self.output_dir),
            radlex_hierarchy=self._radlex_hierarchy,
        )
        fact_store.load()
        current_gc = self.gc_updater.initialize_gc(subject_id)
        llm_calls_v2 = 0
        report_errors: list[dict[str, str]] = []
        successful_reports = 0
        raw_report_chunks: list[str] = []
        total_findings_extracted = 0
        temporal_change_stats = {
            "NEW": 0,
            "UNCHANGED": 0,
            "IMPROVED": 0,
            "WORSENED": 0,
            "RESOLVED": 0,
        }

        # Initialize paired extractor
        paired_extractor = PairedFindingExtractor(
            llm_client=self.extractor.llm_client
            if hasattr(self.extractor, "llm_client")
            else None,
            use_cache=True,
        )

        reports_iter = patient_reports.iterrows()
        if show_progress:
            reports_iter = tqdm(
                list(reports_iter), desc=f"Patient {subject_id} (paired)"
            )

        prev_report_data = None

        for sequence_idx, (_, report) in enumerate(reports_iter, start=1):
            report_date = str(report.get("charttime", "Unknown"))
            hadm_id = str(report.get("hadm_id", "Unknown"))
            report_id = self._safe_report_id(report, sequence_idx)
            study_type = str(report.get("note_type", "RR"))
            report_text = str(report.get("text", ""))

            # Accumulate raw report
            note_id = f"{subject_id}-{study_type}-{report_id}"
            raw_report_chunks.append(
                f"## Report {sequence_idx}\n\n"
                f"- **Date:** {report_date}\n"
                f"- **Note ID:** {note_id}\n"
                f"- **Type:** {study_type}\n\n"
                f"### Report Text\n\n{report_text}\n"
            )

            try:
                if sequence_idx == 1:
                    # First report: individual extraction (consistent entity names)
                    extraction_result = self.extractor.extract(
                        report_text=report_text,
                        chart_date=report_date,
                        study_type=study_type,
                    )
                    print(
                        f"  Report {sequence_idx}: individual extraction ({len(extraction_result.primary_findings)} findings)"
                    )
                else:
                    # Subsequent reports: use paired extraction for BOTH entities and
                    # temporal change classification.  The paired extractor sees both
                    # reports, so it can name entities consistently with Report 1 and
                    # catch cross-report context that individual extraction misses.
                    try:
                        extraction_result = paired_extractor.extract_pair(
                            prev_report_text=prev_report_data["text"],
                            curr_report_text=report_text,
                            prev_date=prev_report_data["date"],
                            curr_date=report_date,
                            prev_study_type=prev_report_data["study_type"],
                            curr_study_type=study_type,
                            prev_report_num=sequence_idx - 1,
                            curr_report_num=sequence_idx,
                        )

                        # Track temporal change stats from paired result
                        if hasattr(extraction_result, "temporal_change_classifications"):
                            pair_changes = extraction_result.temporal_change_classifications
                            for finding in extraction_result.primary_findings:
                                entity = finding.get("entity", "") if isinstance(finding, dict) else ""
                                if entity and entity in pair_changes:
                                    finding["temporal_change"] = pair_changes[entity]
                                    if pair_changes[entity] in temporal_change_stats:
                                        temporal_change_stats[pair_changes[entity]] += 1

                        print(
                            f"  Report {sequence_idx}: paired extraction ({len(extraction_result.primary_findings)} findings)"
                        )
                    except Exception as e:
                        logger.warning(f"Paired extraction failed: {e}")
                        # Fallback to individual extraction
                        extraction_result = self.extractor.extract(
                            report_text=report_text,
                            chart_date=report_date,
                            study_type=study_type,
                        )
                        print(
                            f"  Report {sequence_idx}: individual fallback ({len(extraction_result.primary_findings)} findings)"
                        )

                llm_calls_v2 += 1

            except Exception as e:
                message = (
                    f"Extraction failed for report {report_id}: {type(e).__name__}: {e}"
                )
                print(message)
                report_errors.append(
                    {
                        "report_id": report_id,
                        "report_date": report_date,
                        "error": message,
                    }
                )
                continue

            # Store for next iteration
            prev_report_data = {
                "text": report_text,
                "date": report_date,
                "study_type": study_type,
            }

            # Check for LLM failure note
            llm_failure_note = next(
                (
                    str(item)
                    for item in extraction_result.critical_ambiguities
                    if isinstance(item, str)
                    and item.lower().startswith("llm call failed")
                ),
                None,
            )
            if llm_failure_note:
                report_errors.append(
                    {
                        "report_id": report_id,
                        "report_date": report_date,
                        "error": llm_failure_note,
                    }
                )
            else:
                successful_reports += 1

            # Process findings (same as regular process_patient)
            all_findings = []
            for finding in extraction_result.primary_findings:
                if isinstance(finding, dict):
                    finding["source_report_id"] = report_id
                    finding["source_report_date"] = report_date
                    finding["hadm_id"] = hadm_id
                    finding["report_sequence"] = sequence_idx
                    all_findings.append(finding)

            for negative in extraction_result.significant_negatives:
                if isinstance(negative, dict):
                    negative["source_report_id"] = report_id
                    negative["source_report_date"] = report_date
                    negative["hadm_id"] = hadm_id
                    negative["report_sequence"] = sequence_idx
                    negative["is_negated"] = True
                    all_findings.append(negative)

            # M4B: paired-mode context-bleed filter — drop findings whose
            # evidence is anchored only in the previous report, not the
            # current report (constraints #1-3 from M4 decision gate).
            if sequence_idx > 1:
                before_count = len(all_findings)
                all_findings = self._filter_paired_context_bleed(
                    all_findings, report_text, report_id
                )
                if len(all_findings) < before_count:
                    print(
                        f"  Paired constraint filter: dropped "
                        f"{before_count - len(all_findings)} context-bleed findings "
                        f"({len(all_findings)} kept)"
                    )

            # Phase 2A Step 1: Negation policy filter — drop routine negated
            # normals that don't answer the study's clinical question.
            cleaned = clean_report(report_text)
            all_findings = self._apply_negation_policy_filter(
                all_findings, cleaned.indication
            )

            # Phase 2A Step 2: Sub-finding consolidation — merge child
            # findings into their parent when both appear in the same report.
            all_findings = self._consolidate_sub_findings(all_findings)

            # Phase 2A Step 3: Deduplicate findings within report
            all_findings = self._dedupe_findings(all_findings)

            # P5: evidence-text population fallback.
            # The LLM prompt asks for evidence_text but may not always return it.
            # For any finding missing evidence_text, recover it from the source
            # report using span offsets or entity-name substring matching.
            report_text_lower = report_text.lower()
            for finding in all_findings:
                if isinstance(finding, dict) and not _safe_str(
                    finding.get("evidence_text") or finding.get("negation_language") or ""
                ).strip():
                    # Try span-based recovery first (G5)
                    span_start = int(finding.get("span_start", -1) or -1)
                    span_end = int(finding.get("span_end", -1) or -1)
                    if span_start >= 0 and span_end > span_start and span_end <= len(report_text):
                        finding["evidence_text"] = report_text[span_start:span_end]
                    else:
                        # Try entity-name substring match in report
                        entity = _safe_str(
                            finding.get("entity") or finding.get("finding") or ""
                        ).strip()
                        if entity and len(entity) >= 3:
                            # Search each line for entity name tokens
                            entity_tokens = entity.lower().split()
                            for line in report_text.split("\n"):
                                line_lower = line.lower()
                                if all(t in line_lower for t in entity_tokens if len(t) >= 3):
                                    finding["evidence_text"] = line.strip()
                                    break
                            if not finding.get("evidence_text"):
                                # Last resort: use negation_language
                                finding["evidence_text"] = _safe_str(finding.get("negation_language")).strip()

            # Build oncologic context from the fact graph accumulated so far.
            current_graph = fact_store.serialize()
            report_context = {
                "has_malignancy_history": any(
                    entity.get("entity_type")
                    in ("primary_tumor", "metastasis", "lymph_node_metastasis")
                    or any(
                        term in str(entity.get("canonical_name", "")).lower()
                        for term in ("metast", "tumor", "carcinoma", "malignancy")
                    )
                    for entity in current_graph.get("entities", {}).values()
                    if isinstance(entity, dict)
                    and not entity.get("is_negated", False)
                    and entity.get("status") == "active"
                )
            }

            # Ground and append to Fact Graph
            grounded_findings = []
            for event_index, finding in enumerate(all_findings, start=1):
                grounded_event = self._ground_and_append_finding(
                    finding=finding,
                    fact_store=fact_store,
                    report_date=report_date,
                    hadm_id=hadm_id,
                    report_id=report_id,
                    event_index=event_index,
                    report_context=report_context,
                )
                if grounded_event:
                    grounded_findings.append(grounded_event)
                    total_findings_extracted += 1
                    # Track LLM-assisted grounding calls
                    if grounded_event.get("grounding_method") == "llm_assisted":
                        llm_calls_v2 += 1

            # Invariant check 1: non-zero findings
            if not all_findings and len(report_text.strip()) > 100:
                logger.warning(
                    "INVARIANT: zero findings extracted",
                    extra={"report_id": report_id, "metric": "zero_findings"},
                )

            # Invariant check 3: entity count per report must not exceed 50
            if len(all_findings) > 50:
                logger.warning(
                    "INVARIANT: entity count exceeds 50 — possible hallucination",
                    extra={
                        "report_id": report_id,
                        "metric": "entity_count_spike",
                        "actual": len(all_findings),
                    },
                )

            # Incremental GC render
            if grounded_findings:
                try:
                    current_gc = self.gc_updater.render_from_fact_graph(
                        fact_store.serialize(),
                        mode="incremental",
                        current_gc=current_gc,
                        new_events=grounded_findings,
                    )
                except Exception as e:
                    logger.error(f"GC render failed: {e}")

            if self.save_intermediate:
                intermediate_path = (
                    self.output_dir / f"subject_{subject_id}_{report_id}.md"
                )
                with open(intermediate_path, "w", encoding="utf-8") as f:
                    f.write(current_gc)

        # Final processing (same as regular)
        run_end_time = time.time()

        # Dedupe pass (same as process_patient, but with G2 ablation toggles)
        try:
            if self.use_radlex_merge:
                fact_store.merge_entities_by_radlex()
            if self.use_normalizer:
                dedupe_result = self.normalizer.deduplicate_fact_graph(
                    fact_store.serialize()
                )
                fact_store.replace_graph(dedupe_result.deduplicated_graph)
        except Exception as e:
            logger.error(f"Dedup pass failed: {e}")

        # Clinical dimensions analysis
        try:
            enhanced_graph, clinical_dimensions = (
                self.clinical_dimension_analyzer.analyze(fact_store.serialize())
            )
            fact_store.replace_graph(enhanced_graph)
        except Exception as e:
            logger.error(f"Clinical dimensions analysis failed: {e}")

        # Final GC render
        try:
            final_gc = self.gc_updater.render_from_fact_graph(
                fact_store.serialize(),
                mode="full",
            )
        except Exception as e:
            logger.error(f"Final GC render failed: {e}")
            final_gc = current_gc

        # Progression analysis
        try:
            progression_result = self.progression_analyzer.analyze_fact_graph(
                fact_store.serialize()
            )
            progression = {
                "status": progression_result.disease_status,
                "confidence": progression_result.confidence,
                "evidence": progression_result.key_evidence,
                "summary": progression_result.timeline_summary,
            }
        except Exception as e:
            logger.error(f"Progression analysis failed: {e}")
            progression = {"status": "Unknown", "error": str(e)}

        # Save outputs
        fact_store.save()
        self.gc_updater.save_gc(
            gc_content=final_gc,
            subject_id=subject_id,
            output_dir=str(self.output_dir),
            save_history=True,
        )
        raw_reports_md = (
            f"# Raw Radiology Reports — Patient {subject_id}\n\n"
            f"**Total Reports:** {len(raw_report_chunks)}\n\n---\n\n"
            + "\n---\n\n".join(raw_report_chunks)
        )
        raw_reports_path = self.output_dir / f"subject_{subject_id}_raw_reports.md"
        raw_reports_path.write_text(raw_reports_md, encoding="utf-8")

        # Track progression LLM usage
        try:
            if progression_result.recist_details.get("non_target_llm_used"):
                llm_calls_v2 += 1
        except Exception:
            pass

        # Write detailed outputs (matching process_patient)
        normalized_entities = self._normalized_entities_from_fact_graph(
            fact_store.serialize()
        )
        entities_before_norm = len(fact_store.get_patient_graph().entities)

        analysis_payload = {
            "subject_id": subject_id,
            "processed_at": datetime.now().isoformat(),
            "num_reports": len(patient_reports),
            "num_reports_successful": successful_reports,
            "num_reports_failed": len(report_errors),
            "report_errors": report_errors,
            "normalized_entities": normalized_entities,
            "contradictions": [],
            "entity_deduplication": {
                "merges_applied": getattr(dedupe_result, "merges_applied", []),
                "flagged_ambiguous_pairs": getattr(
                    dedupe_result, "flagged_ambiguous_pairs", []
                ),
            },
            "clinical_dimensions": clinical_dimensions,
            "progression": progression,
            "llm_calls_v2": llm_calls_v2,
            "paired_processing": True,
            "temporal_change_stats": temporal_change_stats,
        }
        results_path = self.output_dir / f"subject_{subject_id}_analysis.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(analysis_payload, f, indent=2)

        # Structured run summary
        grounded_count = sum(
            1
            for e in fact_store.get_patient_graph().entities.values()
            if getattr(e, "radlex_id", None)
        )
        run_summary = {
            "subject_id": subject_id,
            "reports_attempted": len(patient_reports),
            "reports_succeeded": successful_reports,
            "reports_failed": len(report_errors),
            "total_findings_extracted": total_findings_extracted,
            "entities_after_normalization": entities_before_norm,
            "entities_with_radlex_id": grounded_count,
            "llm_calls": llm_calls_v2,
            "run_duration_seconds": round(run_end_time - run_start_time, 1),
            "paired_processing": True,
        }
        summary_path = self.output_dir / f"subject_{subject_id}_run_summary.json"
        summary_path.write_text(json.dumps(run_summary, indent=2), encoding="utf-8")

        print(f"\n✅ Paired processing complete for {subject_id}")
        print(f"   Reports: {successful_reports}/{len(patient_reports)} successful")
        print(f"   Findings: {total_findings_extracted}")
        print(f"   Temporal changes: {temporal_change_stats}")
        print(f"   LLM calls: {llm_calls_v2}")
        print(f"   Time: {int(run_end_time - run_start_time)}s")

        # Build result
        return {
            "subject_id": subject_id,
            "gc": final_gc,
            "progression": progression,
            "fact_graph": fact_store.serialize(),
            "normalized_entities": normalized_entities,
            "metrics": {
                "num_reports_total": len(patient_reports),
                "num_reports_successful": successful_reports,
                "num_reports_failed": len(report_errors),
                "num_findings_extracted": total_findings_extracted,
                "llm_calls_v2": llm_calls_v2,
                "run_time_seconds": int(run_end_time - run_start_time),
                "paired_processing": True,
                "temporal_change_stats": temporal_change_stats,
            },
            "report_errors": report_errors,
        }

    def _ground_and_append_finding(
        self,
        finding: dict,
        fact_store: FactStore,
        report_date: str,
        hadm_id: str,
        report_id: str,
        event_index: int = 1,
        report_context: dict | None = None,
    ) -> dict | None:
        """Ground a single finding and append it to the FactStore.

        Uses the same grounding path as the main process_patient loop:
        EntityGrounder.ground() → FactStore.append_grounded_finding().
        Returns the raw event dict on success, None on failure.
        """
        try:
            surface_form = self._surface_form_for_grounding(finding)
            grounded = self.entity_grounder.ground(
                surface_form=surface_form,
                report_context=report_context,
            )
            grounded_dict = grounded.to_dict()
            grounded_dict["canonical_name"] = normalize_entity_name(
                grounded_dict.get("canonical_name", "")
            )
            event = fact_store.append_grounded_finding(
                finding=finding,
                grounded_entity=grounded_dict,
                report_date=report_date,
                hadm_id=hadm_id,
                report_id=report_id,
                modality=str(finding.get("modality") or "OTHER"),
                event_index=event_index,
            )
            result = event.model_dump(mode="json")
            result["grounding_method"] = grounded.grounding_method
            return result
        except Exception as e:
            logger.warning(f"Grounding failed for '{finding.get('entity', '?')}': {e}")
        return None

    def _prepare_events_for_render(self, grounded_findings: list) -> list:
        """Convert grounded event dicts to a list suitable for incremental GC render."""
        return [gf for gf in grounded_findings if isinstance(gf, dict)]

    def _save_outputs(
        self, subject_id: str, gc: str, fact_store: FactStore, raw_report_chunks: list
    ):
        """Kept for backward compatibility. Saving is now done inline in process_patient_paired."""
        pass
