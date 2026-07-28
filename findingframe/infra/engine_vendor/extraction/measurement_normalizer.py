"""Deterministic measurement parsing shared by FindingFrame consumers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedMeasurement:
    raw: str
    values_mm: list[float]
    max_diameter_mm: float | None
    short_axis_mm: float | None
    unit_source: str | None
    measurement_kind: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TOO_SMALL_RE = re.compile(r"\btoo\s+small\s+to\s+measure\b", re.IGNORECASE)
_MEASUREMENT_RE = re.compile(
    r"(?P<first>\d+(?:\.\d+)?)"
    r"(?P<dims>(?:\s*(?:x|by|×)\s*\d+(?:\.\d+)?){0,3})"
    r"\s*(?P<unit>mm|millimeters?|cm|centimeters?)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _unit_factor(unit: str) -> float | None:
    normalized = unit.strip().lower()
    if normalized in {"mm", "millimeter", "millimeters"}:
        return 1.0
    if normalized in {"cm", "centimeter", "centimeters"}:
        return 10.0
    return None


def normalize_measurement(value: Any, *, finding_type: str | None = None) -> NormalizedMeasurement:
    """Parse raw radiology measurement text into millimeter values.

    The parser is intentionally conservative: it only returns values when a
    unit is attached to the expression. Multi-dimensional values use the
    largest diameter as ``max_diameter_mm``. For lymph nodes, the second
    dimension is exposed as ``short_axis_mm`` when available because RECIST-like
    review uses nodal short axis.
    """
    if isinstance(value, dict):
        raw = str(
            value.get("raw")
            or value.get("text")
            or value.get("raw_text")
            or value.get("display")
            or ""
        ).strip()
        normalized = value.get("normalized_mm")
        if normalized not in (None, ""):
            try:
                parsed = round(float(normalized), 2)
                return NormalizedMeasurement(
                    raw=raw,
                    values_mm=[parsed],
                    max_diameter_mm=parsed,
                    short_axis_mm=parsed if finding_type == "lymph_node_metastasis" else None,
                    unit_source=str(value.get("unit") or "normalized_mm"),
                    measurement_kind="single",
                    warnings=[],
                )
            except (TypeError, ValueError):
                pass
    else:
        raw = str(value or "").strip()

    # Strip prior/previous comparison measurements to focus on current size
    raw = re.sub(r"\([^)]*\b(?:prior|prev|previously|previous)\b[^)]*\)", "", raw, flags=re.IGNORECASE)
    raw = re.split(r"\b(?:prior|prev|previously|previous)\b", raw, maxsplit=1, flags=re.IGNORECASE)[0]

    # Strip location/distance descriptors to prevent overriding actual lesion size
    raw = re.sub(
        r"\b(?:distance\s+(?:from|to)|from)\s+(?:the\s+)?(?:[a-zA-Z_]+\s+){0,3}(?:verge|margin|carina|orifice)\s*(?:of\s*)?\d+(?:\.\d+)?\s*(?:mm|cm|millimeters?|centimeters?)\b",
        "",
        raw,
        flags=re.IGNORECASE
    )
    raw = re.sub(
        r"\bdistance\s+(?:from|to)\s+[^,;]*?\d+(?:\.\d+)?\s*(?:mm|cm|millimeters?|centimeters?)\b",
        "",
        raw,
        flags=re.IGNORECASE
    )

    raw = raw.strip().rstrip(",").strip()

    if not raw:
        return NormalizedMeasurement("", [], None, None, None, "missing", [])

    if _TOO_SMALL_RE.search(raw):
        return NormalizedMeasurement(raw, [], None, None, None, "too_small_to_measure", [])

    values: list[float] = []
    units: list[str] = []
    warnings: list[str] = []
    max_dimension_count = 0

    for match in _MEASUREMENT_RE.finditer(raw):
        unit = match.group("unit")
        factor = _unit_factor(unit)
        if factor is None:
            continue
        numbers = [float(n) for n in _NUMBER_RE.findall(match.group(0))]
        if not numbers:
            continue
        max_dimension_count = max(max_dimension_count, len(numbers))
        values.extend(round(n * factor, 2) for n in numbers)
        units.append(unit.lower())

    if not values:
        warnings.append("no_unit_measurement_found")
        return NormalizedMeasurement(raw, [], None, None, None, "unparsed", warnings)

    unit_source = units[-1] if units else None
    kind = "multi_dimension" if max_dimension_count > 1 else "single"
    if len(values) > max_dimension_count > 0:
        kind = "multiple_measurements"

    short_axis = None
    if finding_type == "lymph_node_metastasis" and len(values) >= 2:
        short_axis = values[1]

    return NormalizedMeasurement(
        raw=raw,
        values_mm=values,
        max_diameter_mm=max(values),
        short_axis_mm=short_axis,
        unit_source=unit_source,
        measurement_kind=kind,
        warnings=warnings,
    )


def measurement_max_mm(value: Any, *, finding_type: str | None = None) -> float | None:
    """Convenience wrapper returning the largest parsed diameter in mm."""
    return normalize_measurement(value, finding_type=finding_type).max_diameter_mm


def normalize_measurement_string(text: str) -> FrameMeasurement:
    """Parse raw measurement text into structured FrameMeasurement."""
    from extraction.finding_frame_schema import FrameMeasurement
    
    normalized = normalize_measurement(text)
    
    if not normalized.values_mm:
        return FrameMeasurement(
            raw=text,
            text=text,
            value=None,
            values=[],
            unit=None,
            normalized_mm=None
        )
        
    return FrameMeasurement(
        raw=text,
        text=text,
        value=normalized.max_diameter_mm,
        values=normalized.values_mm,
        unit=normalized.unit_source,
        normalized_mm=normalized.max_diameter_mm
    )

