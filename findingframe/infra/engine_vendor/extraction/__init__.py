"""
Extraction module for radiology finding extraction and entity normalization.
"""

from .prompts import (
    RADIOLOGY_FINDING_EXTRACTION_PROMPT,
    ENTITY_NORMALIZATION_PROMPT,
    EXTRACTION_EVAL_PROMPT,
    PAIRED_REPORT_EXTRACTION_PROMPT,
)
from .finding_extractor import FindingExtractor, ExtractionCache
from .entity_normalizer import EntityNormalizer
from .hybrid_extractor import HybridExtractor
from .paired_extractor import (
    PairedFindingExtractor,
    PairedExtractionResult,
    process_reports_paired,
)
from .finding_frame_schema import (
    FindingFrame,
    FindingFrameExtractionOutput,
    FrameMeasurement,
)
from .finding_frame_extractor import (
    FindingFrameExtractionResult,
    FindingFrameExtractor,
    dedupe_catch_all_findings,
)
from .finding_type_taxonomy import (
    INITIAL_FINDING_TYPES,
    TAXONOMY_BY_TYPE,
    all_finding_types,
    canonicalize_finding_type,
    concept_terms_for_type,
    get_finding_type_definition,
    is_taxonomy_finding_type,
)

__all__ = [
    "ExtractionCache",
    "FindingExtractor",
    "HybridExtractor",
    "EntityNormalizer",
    "PairedFindingExtractor",
    "PairedExtractionResult",
    "process_reports_paired",
    "FindingFrame",
    "FindingFrameExtractionOutput",
    "FrameMeasurement",
    "FindingFrameExtractionResult",
    "FindingFrameExtractor",
    "dedupe_catch_all_findings",
    "INITIAL_FINDING_TYPES",
    "TAXONOMY_BY_TYPE",
    "all_finding_types",
    "canonicalize_finding_type",
    "concept_terms_for_type",
    "get_finding_type_definition",
    "is_taxonomy_finding_type",
    "RADIOLOGY_FINDING_EXTRACTION_PROMPT",
    "ENTITY_NORMALIZATION_PROMPT",
    "EXTRACTION_EVAL_PROMPT",
    "PAIRED_REPORT_EXTRACTION_PROMPT",
]
