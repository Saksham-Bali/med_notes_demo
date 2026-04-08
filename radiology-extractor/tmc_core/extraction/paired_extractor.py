"""
Paired Report Finding Extractor

Extension to FindingExtractor for chronological paired report processing.
This enables temporal consistency and temporal change classification.

Usage:
    from extraction.paired_extractor import PairedFindingExtractor

    extractor = PairedFindingExtractor()

    # Process first report standalone
    result_1 = extractor.extract(report_1_text, date_1, study_type)

    # Process subsequent reports in pairs
    result_2 = extractor.extract_pair(
        prev_report=report_1,
        curr_report=report_2,
        prev_findings=result_1
    )
"""

import json
import logging
from typing import Any, Optional
from dataclasses import dataclass, asdict

from tmc_core.extraction.finding_extractor import FindingExtractor, ExtractionResult, ExtractionCache
from tmc_core.extraction.prompts import (
    PAIRED_REPORT_EXTRACTION_PROMPT,
    RADIOLOGY_FINDING_EXTRACTION_PROMPT,
)
from tmc_core.extraction.extraction_schema import ExtractionOutput, EXTRACTION_SCHEMA_VERSION
from tmc_core.extraction.report_cleaner import clean_report
from pathlib import Path
import sys

from tmc_core.utils.llm import create_default_llm_client, parse_json_from_text

logger = logging.getLogger("extraction.paired_extractor")


@dataclass
class PairedExtractionResult(ExtractionResult):
    """Extended result with temporal change classification."""

    temporal_change_classifications: dict = (
        None  # entity -> NEW/UNCHANGED/IMPROVED/WORSENED/RESOLVED
    )

    def __post_init__(self):
        if self.temporal_change_classifications is None:
            self.temporal_change_classifications = {}


class PairedFindingExtractor(FindingExtractor):
    """
    Extended extractor for paired report processing with temporal classification.

    Inherits from FindingExtractor for single-report extraction,
    adds extract_pair() for chronological processing.
    """

    def __init__(self, llm_client: Optional[Any] = None, use_cache: bool = True):
        """Initialize the paired finding extractor."""
        super().__init__(llm_client=llm_client, use_cache=use_cache)
        # Separate cache for paired extractions
        self._paired_cache = (
            ExtractionCache(cache_path="./outputs/cache/paired_extraction_cache.json")
            if use_cache
            else None
        )
        # Track cache version for paired processing
        self.PAIRED_CACHE_VERSION = "paired_v1"

    def extract_pair(
        self,
        prev_report_text: str,
        curr_report_text: str,
        prev_date: str,
        curr_date: str,
        prev_study_type: str = "Unknown",
        curr_study_type: str = "Unknown",
        prev_report_num: int = 1,
        curr_report_num: int = 2,
    ) -> PairedExtractionResult:
        """
        Extract findings from current report with knowledge of previous report.

        This enables:
        1. Consistent entity naming across reports
        2. Temporal change classification (NEW/UNCHANGED/IMPROVED/WORSENED/RESOLVED)
        3. Measurement continuity tracking

        Args:
            prev_report_text: Text of the previous (N-1) report
            curr_report_text: Text of the current (N) report
            prev_date: Date of previous report
            curr_date: Date of current report
            prev_study_type: Type of previous study
            curr_study_type: Type of current study
            prev_report_num: Sequential number of previous report
            curr_report_num: Sequential number of current report

        Returns:
            PairedExtractionResult with temporal_change classifications
        """
        # Check paired extraction cache
        if self._paired_cache is not None:
            cache_key = self._paired_cache._key(
                f"{prev_report_text}\n---\n{curr_report_text}",
                f"{prev_date}_{curr_date}",
                f"{prev_study_type}_{curr_study_type}",
            )
            cached = (
                self._paired_cache._data.get(cache_key)
                if self._paired_cache._data
                else None
            )
            if cached:
                logger.debug(
                    "paired extraction cache hit for reports %d->%d",
                    prev_report_num,
                    curr_report_num,
                )
                return PairedExtractionResult(**cached)

        # Clean both reports
        prev_cleaned = clean_report(prev_report_text)
        curr_cleaned = clean_report(curr_report_text)

        prev_extraction_text = prev_cleaned.extraction_text or prev_report_text
        curr_extraction_text = curr_cleaned.extraction_text or curr_report_text

        # Build paired extraction prompt
        prompt = PAIRED_REPORT_EXTRACTION_PROMPT.format(
            previous_report_text=prev_extraction_text,
            prev_date=prev_date,
            prev_num=prev_report_num,
            report_text=curr_extraction_text,
            curr_date=curr_date,
            curr_num=curr_report_num,
            extraction_rules=self._get_extraction_rules(),
        )

        try:
            response_text = self._call_llm(prompt)
        except Exception as e:
            logger.error("Paired extraction LLM call failed: %s", e)
            # Fall back to individual extraction if paired fails
            logger.warning(
                "Falling back to individual extraction for report %d", curr_report_num
            )
            return self._fallback_to_individual(
                curr_report_text, curr_date, curr_study_type, str(e)
            )

        # Parse and validate
        try:
            data = parse_json_from_text(response_text)
            validated = ExtractionOutput.model_validate(data)

            report_metadata = validated.report_metadata.model_dump()
            primary_findings = [f.model_dump() for f in validated.primary_findings]
            significant_negatives = [
                n.model_dump() for n in validated.significant_negatives
            ]
            critical_ambiguities = list(validated.critical_ambiguities)

        except Exception as ve:
            logger.warning("Paired extraction validation failed: %s. Falling back.", ve)
            return self._fallback_to_individual(
                curr_report_text, curr_date, curr_study_type, f"validation_failed: {ve}"
            )

        # Extract temporal change classifications from findings
        temporal_changes = {}
        for finding in primary_findings:
            if isinstance(finding, dict):
                entity = finding.get("entity", "")
                temporal_change = finding.get("temporal_change")
                if temporal_change:
                    temporal_changes[entity] = temporal_change

        # Add modality and normalize measurements
        inferred_modality = self._infer_modality(curr_study_type, curr_report_text)
        for finding in primary_findings:
            if isinstance(finding, dict):
                finding.setdefault("modality", inferred_modality)
                finding["measurement_normalized"] = self._normalize_measurement(finding)
                self._validate_span(finding, curr_extraction_text)

        for negative in significant_negatives:
            if isinstance(negative, dict):
                self._validate_span(negative, curr_extraction_text)

        report_metadata.setdefault("study_type", curr_study_type)
        report_metadata.setdefault("modality", inferred_modality)
        report_metadata["paired_processing"] = True
        report_metadata["prev_report_date"] = prev_date
        report_metadata["prev_report_num"] = prev_report_num

        result = PairedExtractionResult(
            report_metadata=report_metadata,
            primary_findings=primary_findings,
            significant_negatives=significant_negatives,
            overall_confidence=float(
                data.get("overall_extraction_confidence", 0.0) or 0.0
            ),
            critical_ambiguities=critical_ambiguities,
            raw_response=response_text,
            temporal_change_classifications=temporal_changes,
        )

        # Cache the result
        if self._paired_cache is not None:
            cache_key = self._paired_cache._key(
                f"{prev_report_text}\n---\n{curr_report_text}",
                f"{prev_date}_{curr_date}",
                f"{prev_study_type}_{curr_study_type}",
            )
            if self._paired_cache._data is None:
                self._paired_cache._load()
            self._paired_cache._data[cache_key] = asdict(result)
            self._paired_cache._persist()

        return result

    def _fallback_to_individual(
        self, report_text: str, chart_date: str, study_type: str, error_msg: str
    ) -> PairedExtractionResult:
        """Fallback to individual extraction when paired fails."""
        individual_result = self.extract(report_text, chart_date, study_type)

        # Convert to PairedExtractionResult
        return PairedExtractionResult(
            report_metadata={
                **individual_result.report_metadata,
                "paired_processing": False,
                "paired_fallback_reason": error_msg,
            },
            primary_findings=individual_result.primary_findings,
            significant_negatives=individual_result.significant_negatives,
            overall_confidence=individual_result.overall_confidence
            * 0.9,  # Penalty for fallback
            critical_ambiguities=individual_result.critical_ambiguities
            + [f"paired_fallback: {error_msg}"],
            raw_response=individual_result.raw_response,
            temporal_change_classifications={},
        )

    def _get_extraction_rules(self) -> str:
        """Get the extraction rules section for paired prompt."""
        return """
### EXTRACTION RULES (same as single-report)
1. **Extract POSITIVE findings** (masses, lesions, abnormalities)
2. **Extract PRESUMPTIVE findings** ("suspicious for", "concerning for", "likely represents")
3. **Extract DIFFERENTIAL diagnoses** ("differential includes")
4. **Preserve UNCERTAINTY language** (do not convert "suspicious" to "confirmed")
5. **Extract ALL MEASUREMENTS** with units and anatomical location
6. **Extract COMPARISONS** to prior studies ("increased from", "new since", "stable")
7. **Extract CLINICALLY SIGNIFICANT NEGATIVES** ("no evidence of metastasis")
8. **DO NOT summarize** - extract verbatim
9. **DO NOT interpret** - just extract what is stated
10. **Include temporal context** (baseline, interval change, new, resolved)
11. **Do NOT promote clinical history into current findings**

ENTITY NAMING — CRITICAL:
When naming an extracted finding, always name the FINDING not the anatomic structure.
Use the SHORTEST accurate name for the finding type (2–5 words maximum). Do NOT include
measurements, qualifiers like "mild"/"moderate"/"severe", or full anatomical paths in the entity name.
Include anatomy only when it disambiguates the finding.

NEGATION DETECTION — CRITICAL:
For every finding, you MUST set "is_negated": true if the finding is:
  - Explicitly absent: "no hemorrhage", "no effusion", "without infarct"
  - Ruled out: "infarct excluded", "no evidence of mass"
  - Not identified: "no focal abnormality identified", "not seen"
  - Normal: "normal in size", "unremarkable"

If is_negated is true, also capture the exact phrase in "negation_language".
"""


# Convenience function for batch paired processing
def process_reports_paired(
    reports: list[dict],
    extractor: Optional[PairedFindingExtractor] = None,
) -> list[PairedExtractionResult]:
    """
    Process a list of reports chronologically in pairs.

    Args:
        reports: List of report dicts with 'text', 'date', 'study_type', 'report_num'
        extractor: PairedFindingExtractor instance (creates new if None)

    Returns:
        List of PairedExtractionResult, one per report
    """
    if extractor is None:
        extractor = PairedFindingExtractor()

    results = []

    for i, report in enumerate(reports):
        if i == 0:
            # First report: standalone extraction
            result = extractor.extract(
                report_text=report["text"],
                chart_date=report["date"],
                study_type=report.get("study_type", "Unknown"),
            )
            # Convert to PairedExtractionResult
            result = PairedExtractionResult(
                report_metadata={**result.report_metadata, "paired_processing": False},
                primary_findings=result.primary_findings,
                significant_negatives=result.significant_negatives,
                overall_confidence=result.overall_confidence,
                critical_ambiguities=result.critical_ambiguities,
                raw_response=result.raw_response,
                temporal_change_classifications={},
            )
        else:
            # Subsequent reports: paired extraction
            prev_report = reports[i - 1]
            result = extractor.extract_pair(
                prev_report_text=prev_report["text"],
                curr_report_text=report["text"],
                prev_date=prev_report["date"],
                curr_date=report["date"],
                prev_study_type=prev_report.get("study_type", "Unknown"),
                curr_study_type=report.get("study_type", "Unknown"),
                prev_report_num=i,
                curr_report_num=i + 1,
            )

        results.append(result)

    return results
