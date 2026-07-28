"""
Agent 1: Radiology Finding Extractor

Extracts ALL clinical findings from radiology reports with lossless precision.
Uses the configured project LLM provider.
"""

import hashlib
import json
import logging
import os
import sys
import re
from typing import Any, Optional
from dataclasses import dataclass, asdict

from dotenv import load_dotenv

from .prompts import RADIOLOGY_FINDING_EXTRACTION_PROMPT
from .extraction_schema import ExtractionOutput, EXTRACTION_SCHEMA_VERSION
from .report_cleaner import clean_report
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.llm import create_default_llm_client, parse_json_from_text

logger = logging.getLogger("extraction.finding_extractor")


@dataclass
class ExtractionResult:
    """Result of finding extraction from a radiology report."""

    report_metadata: dict
    primary_findings: list
    significant_negatives: list
    overall_confidence: float
    critical_ambiguities: list
    raw_response: str


class ExtractionCache:
    """Disk-backed cache for extraction results, keyed on report text hash.

    Ensures the same report text always produces the same extraction output,
    eliminating 5-10% F1 variance from LLM non-determinism across eval runs.
    """

    CACHE_VERSION = "ext_v8"

    def __init__(self, cache_path: str = "./outputs/cache/extraction_cache.json"):
        self._path = Path(cache_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] | None = None

    def _load(self) -> None:
        if self._data is not None:
            return
        if not self._path.exists():
            self._data = {}
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                self._data = {}
        except Exception:
            self._data = {}

    def _persist(self) -> None:
        assert self._data is not None
        self._path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8"
        )

    @staticmethod
    def _key(report_text: str, chart_date: str, study_type: str) -> str:
        h = hashlib.sha256(report_text.encode("utf-8")).hexdigest()[:16]
        return f"{ExtractionCache.CACHE_VERSION}:{h}:{chart_date}:{study_type}"

    def get(
        self, report_text: str, chart_date: str, study_type: str
    ) -> ExtractionResult | None:
        self._load()
        assert self._data is not None
        key = self._key(report_text, chart_date, study_type)
        entry = self._data.get(key)
        if entry is None:
            return None
        try:
            return ExtractionResult(**entry)
        except Exception:
            return None

    def set(
        self,
        report_text: str,
        chart_date: str,
        study_type: str,
        result: ExtractionResult,
    ) -> None:
        self._load()
        assert self._data is not None
        key = self._key(report_text, chart_date, study_type)
        self._data[key] = asdict(result)
        self._persist()


class FindingExtractor:
    """
    Extracts clinical findings from radiology reports using the configured LLM provider.
    """

    def __init__(self, llm_client: Optional[Any] = None, use_cache: bool = True):
        """Initialize the finding extractor with the configured LLM provider."""
        load_dotenv(dotenv_path="config/.env")
        self.llm_client = llm_client or create_default_llm_client()
        self._cache = ExtractionCache() if use_cache else None

    def extract(
        self, report_text: str, chart_date: str, study_type: str = "Unknown"
    ) -> ExtractionResult:
        """
        Extract findings from a single radiology report.

        Args:
            report_text: The raw radiology report text
            chart_date: Date of the study (YYYY-MM-DD)
            study_type: Type of study (CT, MRI, PET, X-ray, etc.)

        Returns:
            ExtractionResult containing structured findings
        """
        # Check extraction cache first
        if self._cache is not None:
            cached = self._cache.get(report_text, chart_date, study_type)
            if cached is not None:
                logger.debug("extraction cache hit for %s/%s", chart_date, study_type)
                return cached

        # Section cleaning: feed only FINDINGS + IMPRESSION to the LLM
        cleaned = clean_report(report_text)
        extraction_text = cleaned.extraction_text or report_text

        # Build indication constraint for the scope gate
        indication_constraint = ""
        if cleaned.indication:
            indication_constraint = (
                f"\n\nCLINICAL QUESTION / INDICATION: {cleaned.indication}\n"
                "Focus extraction on findings relevant to this clinical question. "
                "Extract primary clinical-question findings even when negated (is_negated=true). "
                "Do not extract incidental routine observations unrelated to the clinical question."
            )

        prompt = RADIOLOGY_FINDING_EXTRACTION_PROMPT.format(
            report_text=extraction_text,
            chart_date=chart_date,
            study_type=study_type,
            modality_instructions=self._get_modality_instructions(
                self._infer_modality(study_type, report_text)
            )
            + indication_constraint,
        )

        try:
            response_text = self._call_llm(prompt)
        except Exception as e:
            # Fallback: try extracting from IMPRESSION section only (shorter, less likely to fail)
            logger.warning(
                "Primary extraction failed (%s), trying IMPRESSION-only fallback", e
            )
            impression_text = self._extract_impression_only(report_text)
            if impression_text:
                fallback_prompt = RADIOLOGY_FINDING_EXTRACTION_PROMPT.format(
                    report_text=impression_text,
                    chart_date=chart_date,
                    study_type=study_type,
                    modality_instructions=(
                        "This is the IMPRESSION section only. Extract ALL findings mentioned."
                    ),
                )
                try:
                    response_text = self._call_llm(fallback_prompt)
                    logger.info(
                        "IMPRESSION-only fallback succeeded (%d chars)",
                        len(response_text),
                    )
                except Exception as e2:
                    return ExtractionResult(
                        report_metadata={
                            "study_date": chart_date,
                            "study_type": study_type,
                        },
                        primary_findings=[],
                        significant_negatives=[],
                        overall_confidence=0.0,
                        critical_ambiguities=[
                            f"LLM call failed (primary+impression fallback): {type(e).__name__}: {e}; "
                            f"fallback: {type(e2).__name__}: {e2}"
                        ],
                        raw_response="",
                    )
            else:
                return ExtractionResult(
                    report_metadata={
                        "study_date": chart_date,
                        "study_type": study_type,
                    },
                    primary_findings=[],
                    significant_negatives=[],
                    overall_confidence=0.0,
                    critical_ambiguities=[f"LLM call failed: {type(e).__name__}: {e}"],
                    raw_response="",
                )

        # Parse JSON from response with Pydantic v2 validation
        try:
            data = parse_json_from_text(response_text)
        except Exception as e:
            # Return a minimal result if parsing fails
            return ExtractionResult(
                report_metadata={"study_date": chart_date, "study_type": study_type},
                primary_findings=[],
                significant_negatives=[],
                overall_confidence=0.0,
                critical_ambiguities=[f"JSON parsing failed: {str(e)}"],
                raw_response=response_text,
            )

        # Validate through Pydantic schema — catches truncation and malformed fields
        try:
            validated = ExtractionOutput.model_validate(data)
            report_metadata = validated.report_metadata.model_dump()
            primary_findings = [f.model_dump() for f in validated.primary_findings]
            significant_negatives = [
                n.model_dump() for n in validated.significant_negatives
            ]
            critical_ambiguities = list(validated.critical_ambiguities)
        except Exception as ve:
            # Fallback to raw dict if validation fails (lenient)
            report_metadata = data.get("report_metadata", {})
            primary_findings = data.get("primary_findings", [])
            significant_negatives = data.get("significant_negatives", [])
            critical_ambiguities = data.get("critical_ambiguities", [])
            critical_ambiguities = (
                list(critical_ambiguities)
                if isinstance(critical_ambiguities, list)
                else []
            )
            critical_ambiguities.append(f"pydantic_validation_warning: {ve}")

        if not isinstance(primary_findings, list):
            primary_findings = []
            critical_ambiguities.append("primary_findings not a list")
        if not isinstance(significant_negatives, list):
            significant_negatives = []
            critical_ambiguities.append("significant_negatives not a list")
        if not isinstance(report_metadata, dict):
            report_metadata = {"study_date": chart_date, "study_type": study_type}
            critical_ambiguities.append("report_metadata not an object")

        # Zero-extraction retry: if both lists are empty and the report is non-trivial,
        # the model may have been confused by the format. Retry once with an explicit
        # plain-film hint to handle FORMAT C (e.g. "LEFT KNEE, THREE VIEWS:") reports
        # that get the generic 'OTHER' modality instructions.
        if (
            not primary_findings
            and not significant_negatives
            and len((report_text or "").strip()) > 100
        ):
            retry_prompt = RADIOLOGY_FINDING_EXTRACTION_PROMPT.format(
                report_text=extraction_text,
                chart_date=chart_date,
                study_type=study_type,
                modality_instructions=(
                    self._get_modality_instructions(
                        self._infer_modality(study_type, report_text)
                    )
                    + indication_constraint
                    + "\n\nNOTE: This report appears to be a plain-film / multi-view study "
                    "(e.g. 'LEFT KNEE, THREE VIEWS'). Apply FORMAT C rules: extract from "
                    "per-region paragraphs AND the IMPRESSION section. "
                    "Returning an empty findings list is NEVER correct for a non-empty report."
                ),
            )
            try:
                retry_response = self._call_llm(retry_prompt)
                retry_data = parse_json_from_text(retry_response)
                retry_findings = retry_data.get("primary_findings", [])
                retry_negatives = retry_data.get("significant_negatives", [])
                if isinstance(retry_findings, list) and isinstance(
                    retry_negatives, list
                ):
                    if retry_findings or retry_negatives:
                        primary_findings = retry_findings
                        significant_negatives = retry_negatives
                        critical_ambiguities.append("zero_extraction_retry_succeeded")
            except Exception:
                pass  # Leave original empty result; don't raise

        inferred_modality = self._infer_modality(
            str(report_metadata.get("study_type") or study_type), report_text
        )
        for finding in primary_findings:
            if not isinstance(finding, dict):
                continue
            finding.setdefault("modality", inferred_modality)
            finding["measurement_normalized"] = self._normalize_measurement(finding)
            self._validate_span(finding, extraction_text)
        for negative in significant_negatives:
            if isinstance(negative, dict):
                self._validate_span(negative, extraction_text)
        report_metadata.setdefault("study_type", study_type)
        report_metadata.setdefault("modality", inferred_modality)

        result = ExtractionResult(
            report_metadata=report_metadata,
            primary_findings=primary_findings,
            significant_negatives=significant_negatives,
            overall_confidence=float(
                data.get("overall_extraction_confidence", 0.0) or 0.0
            ),
            critical_ambiguities=critical_ambiguities,
            raw_response=response_text,
        )

        # Cache the result for reproducibility
        if self._cache is not None:
            self._cache.set(report_text, chart_date, study_type, result)

        return result

    def _infer_modality(self, study_type: str, report_text: str = "") -> str:
        text = (study_type or "").lower()
        if "ct" in text or "computed tomography" in text:
            return "CT"
        if "mri" in text or "mr " in text or text.strip() == "mr":
            return "MRI"
        if "pet" in text:
            return "PET"
        if "ultrasound" in text or re.search(r"\bus\b", text):
            return "US"
        if "mamm" in text:
            return "MAMMO"
        if "x-ray" in text or "xray" in text or "radiograph" in text or "cxr" in text:
            return "XR"
        # Fall back to report text heuristics when study_type is generic (e.g. "RR").
        rtext = (report_text or "").lower()
        if re.search(
            r"(?:pa and lateral|ap and lateral|three views|two views|"
            r"\bap view\b|lateral view|"
            r"(?:left|right|bilateral)\s+(?:knee|ankle|shoulder|wrist|hip|elbow|foot|hand),?\s+(?:three|two|\d)\s+views|"
            r"chest radiograph|portable chest|upright ap)",
            rtext,
        ):
            return "XR"
        if re.search(r"\b(?:helical|mdct|axial|coronal|sagittal|contrast)\b", rtext):
            return "CT"
        if re.search(r"\b(?:t1|t2|flair|dwi|gadolinium|gre)\b", rtext):
            return "MRI"
        return "OTHER"

    def _get_modality_instructions(self, modality: str) -> str:
        """Return modality-specific extraction instructions for the prompt."""
        instructions = {
            "CT": "CT reports have structured FINDINGS then IMPRESSION sections. "
            "Extract measurements in mm or cm. "
            "Look for size comparisons to prior studies.",
            "MRI": "MRI reports have both FINDINGS and IMPRESSION sections. "
            "YOU MUST EXTRACT FROM BOTH — do not skip the FINDINGS section. "
            "The FINDINGS section contains incidental findings that frequently do NOT appear in the IMPRESSION. "
            "You MUST extract from FINDINGS independently of the IMPRESSION. "
            "Incidental findings documented in FINDINGS (e.g. arachnoid cyst, fluid in air cells, "
            "soft tissue prominence) are clinically important and must not be omitted. "
            "T1/T2/FLAIR/DWI sequences may be listed. "
            "Note enhancement patterns after gadolinium. "
            "If the FINDINGS section mentions a structure that is abnormal (e.g. 'fluid', 'cyst', "
            "'prominence', 'enlargement'), always extract it as a finding even if the IMPRESSION "
            "does not repeat it.",
            "XR": "X-ray (plain film) reports often have NO separate FINDINGS section. "
            "The IMPRESSION IS YOUR PRIMARY SOURCE. "
            "Extract all findings stated in the impression. "
            "Returning empty findings for a non-empty impression is ALWAYS wrong.",
            "PET": "PET reports describe metabolic activity. "
            "Look for SUV values, hypermetabolic foci, and comparison to prior.",
            "US": "Ultrasound reports describe echogenicity and vascularity. "
            "Look for size measurements and comparison to prior.",
        }
        return instructions.get(
            modality,
            "Extract ALL findings from the report text without filtering by importance.",
        )

    def _extract_measurement(
        self, text: str
    ) -> tuple[float | None, str | None, float | None]:
        if not text:
            return None, None, None
        from extraction.measurement_normalizer import normalize_measurement, _unit_factor
        norm = normalize_measurement(text)
        if not norm.values_mm:
            return None, None, None
        factor = _unit_factor(norm.unit_source or "mm") or 1.0
        val = norm.max_diameter_mm / factor if norm.max_diameter_mm is not None else None
        return val, norm.unit_source, norm.max_diameter_mm

    def _qualitative_trend(self, text: str) -> str:
        lowered = (text or "").lower()
        if any(
            token in lowered
            for token in ["increased", "increasing", "larger", "slightly larger"]
        ):
            return "increasing"
        if any(token in lowered for token in ["decreased", "decreasing", "smaller"]):
            return "decreasing"
        if any(
            token in lowered
            for token in ["stable", "unchanged", "no significant change"]
        ):
            return "stable"
        if "new" in lowered:
            return "new"
        if "resolved" in lowered:
            return "resolved"
        return "unknown"

    def _normalize_measurement(self, finding: dict) -> dict:
        measurement = finding.get("measurement", {})
        if not isinstance(measurement, dict):
            measurement = {}

        current_text = str(measurement.get("current", "")).strip()
        prior_text = str(measurement.get("prior", "")).strip()
        trend_text = str(measurement.get("trend", "")).strip()
        evidence_text = str(finding.get("evidence_text", "")).strip()

        current_value, current_unit, current_mm = self._extract_measurement(
            current_text
        )
        prior_value, prior_unit, prior_mm = self._extract_measurement(prior_text)

        if current_mm is None and evidence_text:
            current_value, current_unit, current_mm = self._extract_measurement(
                evidence_text
            )

        # Handle comparisons embedded in evidence text: "increased from 2.8 cm".
        if prior_mm is None and evidence_text:
            prior_match = re.search(
                r"(?:from|previously)\s+(\d+(?:\.\d+)?)\s*(mm|cm|in)\b",
                evidence_text.lower(),
            )
            if prior_match:
                p_value = float(prior_match.group(1))
                p_unit = prior_match.group(2)
                prior_value = p_value
                prior_unit = p_unit
                prior_mm = (
                    p_value
                    if p_unit == "mm"
                    else p_value * 10.0
                    if p_unit == "cm"
                    else p_value * 25.4
                )

        trend = self._qualitative_trend(trend_text or current_text or evidence_text)
        is_qualitative = current_mm is None and trend in {
            "increasing",
            "decreasing",
            "stable",
            "new",
            "resolved",
        }
        delta_mm = None
        if current_mm is not None and prior_mm is not None:
            delta_mm = round(current_mm - prior_mm, 2)

        return {
            "value": current_value,
            "unit": current_unit,
            "value_mm": current_mm,
            "is_qualitative": is_qualitative,
            "raw_text": current_text or evidence_text or trend_text or None,
            "trend": trend,
            "prior_value": prior_value,
            "prior_unit": prior_unit,
            "prior_value_mm": round(prior_mm, 2) if prior_mm is not None else None,
            "delta_mm": delta_mm,
        }

    def _validate_span(self, finding: dict, report_text: str) -> None:
        """Validate span_start/span_end against report text. Set to -1 if invalid."""
        if not isinstance(finding, dict):
            return
        try:
            span_start = int(finding.get("span_start", -1) or -1)
            span_end = int(finding.get("span_end", -1) or -1)
        except (TypeError, ValueError):
            span_start, span_end = -1, -1

        if span_start < 0 or span_end < 0 or span_end <= span_start:
            finding["span_start"] = -1
            finding["span_end"] = -1
            return

        if span_end > len(report_text):
            # Allow small overshoot — clamp to text length
            if span_start < len(report_text):
                span_end = len(report_text)
            else:
                finding["span_start"] = -1
                finding["span_end"] = -1
                return

        span_text = report_text[span_start:span_end].lower()
        entity_name = str(finding.get("entity") or finding.get("finding") or "").lower()

        # Check if at least one significant token from the entity appears in the span
        entity_tokens = set(re.sub(r"[^a-z0-9\s]", " ", entity_name).split())
        entity_tokens -= {"the", "a", "an", "of", "in", "on", "is", "are", "no", "not"}
        if not entity_tokens:
            finding["span_start"] = span_start
            finding["span_end"] = span_end
            return

        span_text_clean = re.sub(r"[^a-z0-9\s]", " ", span_text)
        matches = sum(1 for t in entity_tokens if t in span_text_clean)
        if matches == 0:
            finding["span_start"] = -1
            finding["span_end"] = -1
            return

        finding["span_start"] = span_start
        finding["span_end"] = span_end

    # ── Week 3: Structured Outputs JSON schema ──────────────────────────────
    # Using OpenAI Structured Outputs guarantees the response is valid JSON
    # matching this schema, eliminating the 5-10% parse-failure rate of
    # unconstrained text generation. Falls back gracefully via the shared LLM client
    # if the deployment does not support `response_format=json_schema`.
    _EXTRACTION_JSON_SCHEMA: dict = {
        "name": "radiology_extraction",
        "strict": False,  # strict=True would require all fields; False is safer for optional fields
        "schema": {
            "type": "object",
            "properties": {
                "report_metadata": {
                    "type": "object",
                    "properties": {
                        "study_date": {"type": ["string", "null"]},
                        "study_type": {"type": ["string", "null"]},
                        "comparison_study": {"type": ["string", "null"]},
                        "modality": {"type": ["string", "null"]},
                    },
                },
                "primary_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "anatomical_location": {"type": ["string", "null"]},
                            "finding_type": {"type": ["string", "null"]},
                            "measurement": {
                                "type": "object",
                                "properties": {
                                    "current": {"type": ["string", "null"]},
                                    "prior": {"type": ["string", "null"]},
                                    "trend": {"type": ["string", "null"]},
                                },
                            },
                            "modality": {"type": ["string", "null"]},
                            "temporal_qualifier": {"type": ["string", "null"]},
                            "temporal_change": {
                                "type": ["string", "null"],
                                "enum": [
                                    "NEW",
                                    "UNCHANGED",
                                    "IMPROVED",
                                    "WORSENED",
                                    "RESOLVED",
                                    None,
                                ],
                            },
                            "certainty": {"type": "string"},
                            "confidence_score": {"type": "number"},
                            "evidence_text": {"type": ["string", "null"]},
                            "is_negated": {"type": "boolean"},
                            "negation_language": {"type": ["string", "null"]},
                            "comparison_to_prior": {"type": ["string", "null"]},
                        },
                        "required": ["entity", "certainty", "is_negated"],
                    },
                },
                "significant_negatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": ["string", "null"]},
                            "finding": {"type": ["string", "null"]},
                            "evidence_text": {"type": ["string", "null"]},
                            "is_negated": {"type": "boolean"},
                            "negation_language": {"type": ["string", "null"]},
                            "certainty": {"type": ["string", "null"]},
                        },
                    },
                },
                "overall_extraction_confidence": {"type": "number"},
                "critical_ambiguities": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["primary_findings", "significant_negatives"],
        },
    }

    def _extract_impression_only(self, report_text: str) -> str:
        """Extract only the IMPRESSION section text for fallback extraction.

        Returns the impression section content, or the last ~40% of the report
        as a heuristic if no IMPRESSION header is found.
        """
        import re as _re

        # Try to find IMPRESSION: header
        impression_match = _re.search(
            r"(?i)\bIMPRESSION\s*:?\s*\n?(.*?)(?:\n\n[A-Z][A-Z _/]+:|\Z)",
            report_text,
            _re.DOTALL,
        )
        if impression_match:
            text = impression_match.group(1).strip()
            if text:
                return text

        # No IMPRESSION header — take the last third of the text as a fallback
        words = report_text.split()
        if len(words) > 60:
            return " ".join(words[len(words) * 2 // 3 :])
        return ""

    def _call_llm(self, prompt: str, use_structured_output: bool = True) -> str:
        """Call the configured LLM provider with the given prompt.

        When use_structured_output=True (default), requests a Structured Output
        response that is guaranteed to be valid JSON matching _EXTRACTION_JSON_SCHEMA.
        Falls back automatically to unstructured generation if the provider/model
        doesn't support Structured Outputs.
        """
        try:
            schema = self._EXTRACTION_JSON_SCHEMA if use_structured_output else None
            return self.llm_client.chat(
                prompt,
                max_tokens=8000,
                json_schema=schema,
            )
        except Exception as e:
            print(f"ERROR in LLM call: {type(e).__name__}: {e}")
            raise

    def extract_batch(
        self, reports: list[dict], show_progress: bool = True
    ) -> list[ExtractionResult]:
        """
        Extract findings from multiple reports.

        Args:
            reports: List of dicts with 'text', 'charttime', 'category' keys
            show_progress: Whether to show progress bar

        Returns:
            List of ExtractionResult objects
        """
        results = []

        if show_progress:
            from tqdm import tqdm

            reports = tqdm(reports, desc="Extracting findings")

        for report in reports:
            result = self.extract(
                report_text=report.get("text", ""),
                chart_date=str(report.get("charttime", "Unknown")),
                study_type=report.get("category", "Unknown"),
            )
            results.append(result)

        return results
