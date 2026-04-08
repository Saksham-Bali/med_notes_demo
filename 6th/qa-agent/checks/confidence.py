from __future__ import annotations

from models.issue import Issue
from models.response import ClinicalFact


def check_confidence(facts: list[ClinicalFact], min_confidence: float = 0.6) -> list[Issue]:
    issues: list[Issue] = []
    for fact in facts:
        if fact.certainty < min_confidence:
            issues.append(
                Issue(
                    type="LOW_CONFIDENCE",
                    severity="moderate",
                    message=(
                        f"Fact '{fact.entity}' has certainty {fact.certainty:.2f} "
                        f"(below threshold {min_confidence:.2f})."
                    ),
                    evidence=fact.evidence,
                )
            )
    return issues


def count_confidence_checks(facts: list[ClinicalFact]) -> int:
    return len(facts)
