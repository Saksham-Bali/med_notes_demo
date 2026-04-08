from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI

from checks import (
    check_completeness,
    check_confidence,
    check_consistency,
    check_nabh_compliance,
    check_traceability,
    count_completeness_checks,
    count_confidence_checks,
    count_consistency_checks,
    count_nabh_checks,
)
from config import get_settings
from models.audit_trail import AuditTrail
from models.issue import Issue
from models.response import ValidateRequest, ValidateResponse, ValidationResult, ValidationStats
from utils import compute_summary_hash


app = FastAPI(
    title="QA Validation Agent",
    version="1.0.0",
    description=(
        "Validates discharge summaries for completeness, consistency, "
        "confidence, traceability, and NABH-aligned compliance."
    ),
)


def _severity_rank(issue: Issue) -> tuple[int, str]:
    order = {"critical": 0, "moderate": 1, "low": 2}
    return order.get(issue.severity, 9), issue.type


@app.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "agent_id": settings.agent_id}


@app.post("/api/v1/validate", response_model=ValidateResponse)
async def validate_summary(payload: ValidateRequest) -> ValidateResponse:
    settings = get_settings()

    issues: list[Issue] = []
    issues.extend(check_completeness(payload.discharge_summary))
    issues.extend(check_consistency(payload.discharge_summary, payload.source_facts))
    issues.extend(
        check_confidence(
            payload.source_facts,
            min_confidence=settings.low_confidence_threshold,
        )
    )

    if settings.enable_nabh_checks:
        issues.extend(check_nabh_compliance(payload.discharge_summary))

    traceability = await check_traceability(
        payload.discharge_summary,
        payload.source_facts,
        settings,
    )
    issues.extend(traceability.issues)
    issues.sort(key=_severity_rank)

    checks_run = (
        count_completeness_checks()
        + count_consistency_checks(payload.discharge_summary, payload.source_facts)
        + count_confidence_checks(payload.source_facts)
        + (count_nabh_checks(payload.discharge_summary) if settings.enable_nabh_checks else 0)
        + traceability.checks_run
    )

    stats = ValidationStats(
        total_checks_run=checks_run,
        passed=max(checks_run - len(issues), 0),
        failed=len(issues),
        critical_failures=sum(1 for issue in issues if issue.severity == "critical"),
    )
    audit_trail = AuditTrail(
        validation_id=f"VAL-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks_performed=[
            "completeness",
            "consistency",
            "confidence",
            "traceability",
            "nabh",
        ],
        summary_hash=compute_summary_hash(payload.discharge_summary),
        traceability_mode=traceability.mode_used,
        traceability_model=settings.traceability_model if "llm" in traceability.mode_used else None,
    )

    return ValidateResponse(
        agent_id=settings.agent_id,
        result=ValidationResult(
            verdict="FAIL" if issues else "PASS",
            issues=issues,
            stats=stats,
            audit_trail=audit_trail,
        ),
    )
