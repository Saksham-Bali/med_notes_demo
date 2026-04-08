"""
RadiologyExtractor: wraps HybridExtractor + EntityGrounder as a stateless
single-report extraction pipeline.

Replicates the flow from PatientProcessor.process_patient() but for a single
report (or report pair), without the fact-graph/GC machinery.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

# Ensure tmc_core is importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from tmc_core.extraction import HybridExtractor, EntityNormalizer
from tmc_core.entity_grounding import EntityGrounder
from tmc_core.extraction.report_cleaner import clean_report

logger = logging.getLogger("radiology_extractor.extractor")


class RadiologyExtractor:
    """
    Stateless single-report extraction wrapper.

    Initialized once at service startup; the extract() method is thread-safe
    for concurrent requests (the underlying extractors do not mutate shared state
    during inference).
    """

    def __init__(self) -> None:
        logger.info("Initializing RadiologyExtractor …")
        self.extractor = HybridExtractor()
        self.grounder = EntityGrounder(
            use_vector_grounding=False,
            use_scispacy=False,
        )
        self.normalizer = EntityNormalizer()
        logger.info("RadiologyExtractor ready.")

    def extract(
        self,
        report_text: str,
        prior_report_text: str | None,
        report_id: str,
        report_date: str,
        modality: str,
        body_region: str,
        hadm_id: str,
    ) -> list[dict]:
        """
        Extract and ground findings from a single radiology report.

        Args:
            report_text: Full text of the current radiology report.
            prior_report_text: Full text of the immediately preceding report,
                or None if this is the first report.
            report_id: Identifier string for the current report.
            report_date: ISO-8601 date string for the current report.
            modality: Imaging modality (CT, MRI, PET, XR, US, …).
            body_region: Anatomical region (chest, abdomen, head_neck, …).
            hadm_id: Hospital admission ID (may be empty string).

        Returns:
            A list of grounded finding dicts, each enriched with ontology IDs
            and canonical names from the EntityGrounder.
        """
        if not report_text or not report_text.strip():
            return []

        # ── Step 1: Extract findings via hybrid rule + LLM extractor ──────────
        try:
            extraction_result = self.extractor.extract(
                report_text=report_text,
                chart_date=report_date,
                study_type=modality or "Unknown",
            )
        except Exception as exc:
            logger.error("Extraction failed for report %s: %s", report_id, exc)
            return []

        # ── Step 2: Normalise significant negatives to finding dicts ──────────
        all_findings: list[dict] = []
        for finding in extraction_result.primary_findings:
            if isinstance(finding, dict):
                all_findings.append(finding)

        for negative in extraction_result.significant_negatives:
            normalised = self._normalise_significant_negative(negative)
            if normalised:
                all_findings.append(normalised)

        all_findings = self._dedupe_findings(all_findings)

        # ── Step 3: Negation policy filter ────────────────────────────────────
        cleaned = clean_report(report_text)
        all_findings = self._apply_negation_policy_filter(
            all_findings, cleaned.indication
        )

        if not all_findings:
            logger.debug("No findings after policy filter for report %s", report_id)
            return []

        # ── Step 4: Ground each finding against RadLex / SNOMED ───────────────
        # Build a minimal report context so the oncologic gate can function.
        # For single-report mode we default to no prior malignancy context.
        report_context: dict = {"has_malignancy_history": False}

        grounded_findings: list[dict] = []
        for finding in all_findings:
            surface_form = self._surface_form_for_grounding(finding)
            try:
                grounded = self.grounder.ground(
                    surface_form=surface_form,
                    report_context=report_context,
                )
            except Exception as exc:
                logger.warning(
                    "Grounding failed for '%s' in report %s: %s",
                    surface_form,
                    report_id,
                    exc,
                )
                grounded = None

            # Merge grounding result back into the finding dict
            enriched = dict(finding)
            if grounded is not None:
                enriched["radlex_id"] = grounded.radlex_id
                enriched["radlex_label"] = grounded.radlex_label
                enriched["snomed_id"] = grounded.snomed_id
                enriched["canonical_name"] = grounded.canonical_name
                enriched["grounding_method"] = grounded.grounding_method
                enriched["grounding_confidence"] = grounded.grounding_confidence
            else:
                enriched.setdefault("radlex_id", None)
                enriched.setdefault("snomed_id", None)
                enriched.setdefault("canonical_name", surface_form)
                enriched["grounding_method"] = "error"
                enriched["grounding_confidence"] = 0.0

            # Propagate modality and report metadata into the finding
            enriched.setdefault("modality", modality)
            enriched.setdefault(
                "body_region",
                self._infer_body_region(enriched, body_region),
            )
            enriched["source_report_id"] = report_id
            enriched["report_date"] = report_date
            enriched["hadm_id"] = hadm_id

            grounded_findings.append(enriched)

        return grounded_findings

    # ------------------------------------------------------------------
    # Private helpers (replicated from PatientProcessor)
    # ------------------------------------------------------------------

    _CRITICAL_NEGATED_KEYWORDS = frozenset(
        {
            "metastasis", "metastases", "metastatic", "tumor", "tumour",
            "carcinoma", "malignancy", "malignant", "cancer", "neoplasm",
            "neoplastic", "lesion", "mass", "lymphadenopathy", "recurrence",
            "progression", "hemorrhage", "haemorrhage", "thrombosis",
            "embolism", "infarct", "infarction", "pneumothorax", "fracture",
            "dislocation", "hydrocephalus", "midline", "shift", "herniation",
            "enhancement", "effusion", "obstruction", "abnormality",
        }
    )

    def _normalise_significant_negative(self, negative: dict) -> dict | None:
        """Convert a significant_negative entry into a normalised finding dict."""
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
            "evidence_text": negative.get("evidence_text") or negation_language,
        }

    def _dedupe_findings(self, findings: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        seen: set[tuple] = set()
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            key = (
                str(
                    finding.get("entity")
                    or finding.get("entity_name")
                    or finding.get("finding")
                    or ""
                ).strip().lower(),
                str(finding.get("anatomical_location") or "").strip().lower(),
                bool(finding.get("is_negated", False)),
                str(finding.get("negation_language") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped

    def _apply_negation_policy_filter(
        self,
        findings: list[dict],
        indication: str,
    ) -> list[dict]:
        """Drop routine negated normals unrelated to the clinical indication."""
        if not findings:
            return findings
        if not indication or not indication.strip():
            return findings

        indication_tokens = set(
            re.sub(r"[^a-z0-9\s]", " ", indication.lower()).split()
        )

        kept: list[dict] = []
        for finding in findings:
            if not isinstance(finding, dict):
                kept.append(finding)
                continue
            is_negated = bool(finding.get("is_negated", False))
            if not is_negated:
                kept.append(finding)
                continue
            entity_name = str(
                finding.get("entity") or finding.get("finding") or ""
            ).lower()
            entity_tokens = set(
                re.sub(r"[^a-z0-9\s]", " ", entity_name).split()
            )
            if entity_tokens & self._CRITICAL_NEGATED_KEYWORDS:
                kept.append(finding)
                continue
            if indication_tokens and (entity_tokens & indication_tokens):
                kept.append(finding)
                continue
            # Drop routine negated normal
        return kept

    def _surface_form_for_grounding(self, finding: dict) -> str:
        """Derive the surface form to pass to the entity grounder."""
        surface_form = str(
            finding.get("entity")
            or finding.get("anatomical_location")
            or finding.get("finding_type")
            or "unspecified finding"
        ).strip()
        evidence_text = str(
            finding.get("evidence_text") or finding.get("negation_language") or ""
        ).strip()
        _AMBIGUOUS_ENTITY_NAMES = {
            "bone", "osseous", "skeletal", "abnormal", "abnormality",
        }
        if surface_form.lower() not in _AMBIGUOUS_ENTITY_NAMES or not evidence_text:
            return surface_form
        cleaned = re.sub(
            r"^(?:there is|there are)\s+no\s+|^no evidence of\s+|^no\s+|^without\s+",
            "",
            evidence_text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\s+(?:is seen|are seen|identified|noted|present|apparent)\.?\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" .")
        return cleaned or surface_form

    def _infer_body_region(self, finding: dict, fallback: str) -> str:
        """Use finding entity name to infer body region, falling back to the request value."""
        from tmc_core.entity_grounding import infer_body_region
        entity = str(
            finding.get("entity")
            or finding.get("canonical_name")
            or finding.get("entity_name")
            or ""
        )
        anatomical = str(finding.get("anatomical_location") or "")
        region = infer_body_region(entity, anatomical)
        return region if region != "other" else (fallback or "other")
