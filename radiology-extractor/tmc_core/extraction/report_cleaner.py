"""
Report cleaner: section parser and clinical-question scope gate.

Splits radiology reports into sections and feeds only FINDINGS/IMPRESSION
to the extraction LLM. Parses INDICATION for the scope gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Standard MIMIC-IV radiology report section headers
_SECTION_PATTERNS = [
    r"(?:CLINICAL\s+)?HISTORY\s*:",
    r"INDICATION\s*:",
    r"REASON\s+FOR\s+(?:EXAM(?:INATION)?|STUDY)\s*:",
    r"COMPARISON\s*:",
    r"TECHNIQUE\s*:",
    r"PROCEDURE\s*:",
    r"CLINICAL\s+INFORMATION\s*:",
    r"FINDINGS\s*:",
    r"IMPRESSION\s*:",
    r"CONCLUSION\s*:",
    r"RECOMMENDATION\s*:",
    r"WET\s+READ\s*:",
    r"ADDENDUM\s*:",
    # Study-type / modality headers that contain findings (MIMIC-IV common patterns)
    r"(?:NON-?CONTRAST|CONTRAST(?:-ENHANCED)?)\s+(?:HEAD|CHEST|ABDOM\w*|PELVI\w*)\s+(?:CT|MRI?)\s*:",
    r"CT\s+(?:HEAD|CHEST|ABDOM\w*|PELVI\w*)\s+(?:WITH(?:OUT)?\s+)?(?:IV\s+)?CONTRAST\s*:",
    r"(?:LEFT|RIGHT|BILATERAL)\s+\w+,?\s+(?:THREE|TWO|FOUR|FIVE|MULTIPLE)\s+VIEWS?\s*:",
    r"MRI?\s+(?:OF\s+(?:THE\s+)?)?(?:BRAIN|HEAD|CHEST|SPINE|ABDOM\w*|PELVI\w*)\s*[.:]",
    r"PA\s+AND\s+LATERAL\s+(?:CHEST|VIEWS?)\s*[,:]",
    r"C-?SPINE,?\s+(?:TWO|THREE|FOUR|MULTIPLE)\s+VIEWS?\s*:",
    r"(?:T|L|TH?ORACIC|LUMBAR|THORACOLUMBAR)-?SPINE\s*[,:]",
    # MRI brain/neuro-specific headers
    r"(?:DWI|FLAIR|T1|T2|SWI|PWI|ADC|DTI|MRS?)\s+(?:FINDINGS?|SEQUENCES?|SERIES?)\s*:",
    r"SPECTROSCOPY\s*:",
    r"PERFUSION\s+(?:FINDINGS?|STUDY|IMAGING)\s*:",
    r"POST(?:-|\s+)?(?:CONTRAST|GADOLINIUM)\s+(?:FINDINGS?|SEQUENCES?)\s*:",
    # Mammography / breast imaging
    r"(?:RIGHT|LEFT|BILATERAL)\s+BREAST\s+(?:FINDINGS?|ULTRASOUND|MRI?|MAMMOGRAPH(?:Y|IC))\s*:",
    r"MAMMOGRAPH(?:Y|IC)\s+(?:FINDINGS?|REPORT)\s*:",
    r"BREAST\s+(?:FINDINGS?|COMPOSITION|DENSITY)\s*:",
    # Ultrasound headers
    r"ULTRASOUND\s+(?:FINDINGS?|OF\s+(?:THE\s+)?(?:\w+))\s*:",
    r"(?:RENAL|HEPATIC|THYROID|TESTICULAR|PELVIC)\s+ULTRASOUND\s*:",
    # Nuclear medicine / PET
    r"PET(?:/CT)?\s+(?:FINDINGS?|RESULTS?)\s*:",
    r"NUCLEAR\s+MEDICINE\s*:",
    # Vascular
    r"VASCULAR\s+(?:FINDINGS?|ANATOMY|ASSESSMENT)\s*:",
    r"(?:CT|MR)\s+ANGIOGRAPH(?:Y|IC|Y\s+FINDINGS?)\s*:",
]

_SECTION_RE = re.compile(
    r"^\s*(" + "|".join(_SECTION_PATTERNS) + r")",
    re.MULTILINE | re.IGNORECASE,
)

# Sections to KEEP for extraction (FINDINGS + IMPRESSION + CONCLUSION)
_EXTRACTION_SECTIONS = {"findings", "impression", "conclusion"}

# Sections that contain the clinical question / indication
_INDICATION_SECTIONS = {"indication", "reason for exam", "reason for examination",
                        "reason for study", "clinical history", "history",
                        "clinical information"}


@dataclass
class CleanedReport:
    """Result of report cleaning."""
    extraction_text: str  # FINDINGS + IMPRESSION only
    indication: str  # Parsed INDICATION/REASON section
    full_text: str  # Original full text
    sections_found: list[str]  # Section headers found


def _normalize_header(header: str) -> str:
    """Normalize a section header to a canonical key."""
    h = re.sub(r"\s*[:.]\s*$", "", header.strip()).lower()
    h = re.sub(r"\s+", " ", h)
    if "indication" in h or "reason for" in h:
        return "indication"
    if "history" in h or "clinical information" in h:
        return "history"
    if "comparison" in h:
        return "comparison"
    if "technique" in h or "procedure" in h:
        return "technique"
    if "findings" in h:
        return "findings"
    if "impression" in h:
        return "impression"
    if "conclusion" in h:
        return "conclusion"
    if "recommendation" in h:
        return "recommendation"
    # Study-type / modality headers that contain findings
    if any(kw in h for kw in ("ct", "mri", "mr ", "views", "spine",
                               "pa and lateral", "chest", "head",
                               "abdomen", "pelvis", "knee", "brain",
                               "breast", "mammograph", "ultrasound", "vascular",
                               "angiograph", "spectroscopy", "perfusion",
                               "dwi", "flair", "post-contrast", "post contrast",
                               "post gadolinium", "nuclear medicine", "pet")):
        return "findings"
    return h


def clean_report(report_text: str) -> CleanedReport:
    """
    Parse a radiology report into sections and return only the
    clinically relevant sections for extraction.
    """
    if not report_text or not report_text.strip():
        return CleanedReport(
            extraction_text="",
            indication="",
            full_text=report_text or "",
            sections_found=[],
        )

    # Find all section boundaries
    matches = list(_SECTION_RE.finditer(report_text))

    if not matches:
        # No section headers found — return full text (e.g. plain-film reports)
        return CleanedReport(
            extraction_text=report_text.strip(),
            indication="",
            full_text=report_text,
            sections_found=[],
        )

    # Build section map
    sections: dict[str, str] = {}
    headers_found: list[str] = []

    for i, match in enumerate(matches):
        header = _normalize_header(match.group(1))
        headers_found.append(header)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(report_text)
        content = report_text[start:end].strip()
        # If same section appears multiple times, concatenate
        if header in sections:
            sections[header] += "\n" + content
        else:
            sections[header] = content

    # Build extraction text from FINDINGS + IMPRESSION + CONCLUSION
    extraction_parts: list[str] = []
    for section_key in ["findings", "impression", "conclusion"]:
        if section_key in sections and sections[section_key]:
            extraction_parts.append(sections[section_key])

    # If no FINDINGS or IMPRESSION found, fall back to full text
    # (this handles reports that don't use standard headers)
    extraction_text = "\n\n".join(extraction_parts) if extraction_parts else report_text.strip()

    # Parse indication
    indication = ""
    for ind_key in ["indication", "history"]:
        if ind_key in sections and sections[ind_key]:
            indication = sections[ind_key]
            break

    return CleanedReport(
        extraction_text=extraction_text,
        indication=indication,
        full_text=report_text,
        sections_found=headers_found,
    )
