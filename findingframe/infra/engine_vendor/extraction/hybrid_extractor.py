"""
Hybrid finding extractor: rules first, LLM for the rest.

Routes high-confidence findings through the rule-based extractor (zero LLM
cost) and sends only ambiguous or complex sentences to the LLM. This reduces
per-report LLM cost while maintaining extraction quality.

Strategy:
1. Run rule extractor on full report
2. If coverage is high enough (>= 80% of sentences matched), skip LLM
3. Otherwise, run LLM extractor on full report and merge results
4. Deduplicate by span overlap AND label-token Jaccard
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from .finding_extractor import ExtractionResult, FindingExtractor
from .rule_extractor import RuleExtractor


logger = logging.getLogger("extraction.hybrid")

# If rules cover >= this fraction of sentences, skip LLM entirely.
# Set to 1.0 to always run LLM — extractions are cached, so the LLM cost
# is paid only once per unique report text.  Running both ensures the LLM's
# nuanced findings (e.g. tibial_lateral_translocation) are never lost.
COVERAGE_THRESHOLD = 1.0

# Minimum span overlap ratio to consider two findings duplicates
DEDUP_OVERLAP_THRESHOLD = 0.5

# Jaccard threshold for label-token dedup (catches "right hemidiaphragm
# elevation" vs "elevation of right hemidiaphragm" as duplicates)
LABEL_JACCARD_DEDUP_THRESHOLD = 0.70


def _normalize_tokens(text: str) -> frozenset[str]:
    """Split text into lower-case tokens for Jaccard comparison."""
    return frozenset(re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split())


def _label_jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two finding label token sets."""
    ta = _normalize_tokens(a)
    tb = _normalize_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _spans_overlap(a: dict, b: dict) -> bool:
    """Check if two findings have overlapping character spans."""
    a_start = a.get("span_start")
    a_end = a.get("span_end")
    b_start = b.get("span_start")
    b_end = b.get("span_end")

    if any(v is None for v in (a_start, a_end, b_start, b_end)):
        # Fall back to entity name comparison
        a_name = (a.get("entity_name") or "").lower().strip()
        b_name = (b.get("entity_name") or "").lower().strip()
        return a_name == b_name and bool(a_name)

    overlap_start = max(a_start, b_start)
    overlap_end = min(a_end, b_end)
    if overlap_start >= overlap_end:
        return False

    overlap_len = overlap_end - overlap_start
    a_len = max(a_end - a_start, 1)
    b_len = max(b_end - b_start, 1)
    return (overlap_len / min(a_len, b_len)) >= DEDUP_OVERLAP_THRESHOLD


def _finding_confidence(f: dict) -> float:
    """Extract a confidence score from a finding dict."""
    # Rule-based findings have explicit confidence; LLM findings use certainty
    if f.get("extraction_method") == "rule_based":
        return float(f.get("confidence", 0.85) or 0.85)
    # LLM findings: treat confidence_score or fallback to 0.80
    return float(f.get("confidence_score", 0.80) or 0.80)


def _finding_label(f: dict) -> str:
    """Get the best label string for a finding."""
    return (
        f.get("entity_name")
        or f.get("finding_type")
        or f.get("evidence_text")
        or ""
    ).lower().strip()


def _merge_and_dedup(
    rule_findings: list[dict],
    llm_findings: list[dict],
) -> list[dict]:
    """Merge rule and LLM findings with two dedup passes.

    Pass 1: span overlap — LLM wins on overlapping spans.
    Pass 2: label Jaccard — if two findings have ≥0.70 token overlap,
            keep the one with higher confidence, discard the other.
    """
    # Pass 1: span-based merge (LLM takes priority on overlaps)
    merged = list(llm_findings)
    for rf in rule_findings:
        is_duplicate = any(_spans_overlap(rf, lf) for lf in llm_findings)
        if not is_duplicate:
            merged.append(rf)

    # Pass 2: label-token Jaccard dedup across all merged findings
    if len(merged) <= 1:
        return merged

    # Sort by confidence descending so higher-confidence findings survive
    merged.sort(key=_finding_confidence, reverse=True)
    deduplicated: list[dict] = []
    for f in merged:
        f_label = _finding_label(f)
        if not f_label:
            deduplicated.append(f)
            continue
        is_dup = False
        for kept in deduplicated:
            kept_label = _finding_label(kept)
            if _label_jaccard(f_label, kept_label) >= LABEL_JACCARD_DEDUP_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            deduplicated.append(f)

    return deduplicated


class HybridExtractor:
    """Extracts findings using rules first, then LLM for remaining gaps.

    Usage:
        extractor = HybridExtractor()
        result = extractor.extract(report_text, chart_date, study_type)
        # result is a standard ExtractionResult
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        coverage_threshold: float = COVERAGE_THRESHOLD,
    ):
        self.rule_extractor = RuleExtractor()
        self.llm_extractor = FindingExtractor(llm_client=llm_client)
        self.coverage_threshold = coverage_threshold
        self._stats = {
            "rule_only": 0,
            "hybrid": 0,
            "llm_only": 0,
            "rule_findings_total": 0,
            "llm_findings_total": 0,
            "dedup_removed": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def extract(
        self,
        report_text: str,
        chart_date: str,
        study_type: str = "Unknown",
    ) -> ExtractionResult:
        """Extract findings using hybrid rule + LLM approach.

        Returns an ExtractionResult identical in format to FindingExtractor.
        """
        # Step 1: Rule-based extraction
        rule_result = self.rule_extractor.extract(report_text)
        rule_formatted = self.rule_extractor.to_extraction_format(
            rule_result, chart_date, study_type
        )
        rule_primary = rule_formatted["primary_findings"]
        rule_negatives = rule_formatted["significant_negatives"]
        n_rule = len(rule_primary) + len(rule_negatives)
        self._stats["rule_findings_total"] += n_rule

        # Step 2: Decide whether to call LLM
        if (
            rule_result.coverage_ratio >= self.coverage_threshold
            and len(rule_result.findings) >= 2
        ):
            self._stats["rule_only"] += 1
            logger.info(
                "rule_only: %d findings (coverage=%.2f)",
                n_rule,
                rule_result.coverage_ratio,
            )
            return ExtractionResult(
                report_metadata=rule_formatted["report_metadata"],
                primary_findings=rule_primary,
                significant_negatives=rule_negatives,
                overall_confidence=rule_formatted["overall_extraction_confidence"],
                critical_ambiguities=["extraction_method: rule_only"],
                raw_response="",
            )

        # Step 3: Run LLM extractor on full report
        llm_result = self.llm_extractor.extract(report_text, chart_date, study_type)
        n_llm = len(llm_result.primary_findings) + len(llm_result.significant_negatives)
        self._stats["llm_findings_total"] += n_llm

        # Step 4: Merge + dedup (LLM takes priority on overlaps,
        # Jaccard dedup catches same-entity different-surface-form dupes)
        if rule_result.findings:
            self._stats["hybrid"] += 1
            pre_dedup_primary = len(rule_primary) + len(llm_result.primary_findings)
            pre_dedup_negatives = len(rule_negatives) + len(llm_result.significant_negatives)

            merged_primary = _merge_and_dedup(rule_primary, llm_result.primary_findings)
            merged_negatives = _merge_and_dedup(rule_negatives, llm_result.significant_negatives)

            removed = (pre_dedup_primary - len(merged_primary)) + (
                pre_dedup_negatives - len(merged_negatives)
            )
            self._stats["dedup_removed"] += removed

            logger.info(
                "hybrid: rule=%d llm=%d merged=%d (removed %d dupes)",
                n_rule,
                n_llm,
                len(merged_primary) + len(merged_negatives),
                removed,
            )

            ambiguities = list(llm_result.critical_ambiguities) + [
                f"extraction_method: hybrid (rule={n_rule}, llm={n_llm}, dedup_removed={removed})"
            ]
            return ExtractionResult(
                report_metadata=llm_result.report_metadata,
                primary_findings=merged_primary,
                significant_negatives=merged_negatives,
                overall_confidence=max(
                    llm_result.overall_confidence,
                    rule_formatted["overall_extraction_confidence"],
                ),
                critical_ambiguities=ambiguities,
                raw_response=llm_result.raw_response,
            )

        # No rule findings — pure LLM
        self._stats["llm_only"] += 1
        logger.info("llm_only: %d findings", n_llm)
        return llm_result
