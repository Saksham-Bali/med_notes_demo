from __future__ import annotations

import json
from dataclasses import dataclass

from config import Settings
from models.issue import Issue
from models.response import ClinicalFact, DischargeSummary
from utils import fact_text, lexical_match, section_claims


@dataclass
class TraceabilityOutcome:
    issues: list[Issue]
    checks_run: int
    mode_used: str


async def check_traceability(
    summary: DischargeSummary,
    facts: list[ClinicalFact],
    settings: Settings,
) -> TraceabilityOutcome:
    claims = section_claims(summary)
    if settings.traceability_mode == "disabled" or not claims:
        return TraceabilityOutcome(issues=[], checks_run=len(claims), mode_used="disabled")

    should_try_llm = settings.traceability_mode in {"auto", "llm"} and bool(settings.azure_api_key)
    if should_try_llm:
        try:
            return await _llm_traceability_check(claims, facts, settings)
        except Exception:
            if settings.traceability_mode == "llm":
                fallback = _heuristic_traceability_check(claims, facts)
                fallback.issues.insert(
                    0,
                    Issue(
                        type="TRACEABILITY_BACKEND",
                        severity="moderate",
                        section="brief_summary",
                        message="LLM traceability check failed; heuristic fallback was used instead.",
                    ),
                )
                fallback.mode_used = "heuristic-fallback"
                return fallback

    return _heuristic_traceability_check(claims, facts)


def _heuristic_traceability_check(
    claims: list[dict[str, str]],
    facts: list[ClinicalFact],
) -> TraceabilityOutcome:
    fact_texts = [fact_text(fact) for fact in facts]
    issues: list[Issue] = []

    if not fact_texts:
        for claim in claims:
            issues.append(
                Issue(
                    type="UNSUPPORTED_CLAIM",
                    severity="moderate",
                    section=claim["section"],
                    message=f"Claim '{claim['claim']}' cannot be traced because no source facts were supplied.",
                )
            )
        return TraceabilityOutcome(issues=issues, checks_run=len(claims), mode_used="heuristic")

    for claim in claims:
        if not any(lexical_match(claim["claim"], candidate, min_overlap=2) for candidate in fact_texts):
            issues.append(
                Issue(
                    type="UNSUPPORTED_CLAIM",
                    severity="moderate",
                    section=claim["section"],
                    message=f"Claim '{claim['claim']}' is not traceable to the provided source facts.",
                )
            )

    return TraceabilityOutcome(issues=issues, checks_run=len(claims), mode_used="heuristic")


async def _llm_traceability_check(
    claims: list[dict[str, str]],
    facts: list[ClinicalFact],
    settings: Settings,
) -> TraceabilityOutcome:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.openrouter_api_key,
        timeout=settings.traceability_timeout_seconds,
    )

    system_prompt = (
        "You validate clinical discharge-summary traceability. "
        "Return JSON only with the shape "
        '{"unsupported_claims":[{"claim":"...","section":"...","reason":"...","severity":"critical|moderate"}]}. '
        "Mark a claim unsupported only when the provided source facts do not substantiate it."
    )
    user_prompt = json.dumps(
        {
            "claims": claims,
            "source_facts": [fact.model_dump(mode="json") for fact in facts],
        },
        ensure_ascii=True,
        indent=2,
    )

    response = await client.chat.completions.create(
        model=settings.traceability_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    parsed = _parse_traceability_json(response.choices[0].message.content or "")
    issues = [
        Issue(
            type="UNSUPPORTED_CLAIM",
            severity=entry.get("severity", "moderate"),
            section=entry.get("section"),
            message=(
                f"Claim '{entry.get('claim', 'unknown claim')}' is not traceable to source facts. "
                f"{entry.get('reason', '').strip()}".strip()
            ),
        )
        for entry in parsed.get("unsupported_claims", [])
    ]
    return TraceabilityOutcome(issues=issues, checks_run=len(claims), mode_used="llm")


def _parse_traceability_json(raw_text: str) -> dict[str, object]:
    raw_text = raw_text.strip()
    if not raw_text:
        return {"unsupported_claims": []}
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"unsupported_claims": []}
        return json.loads(raw_text[start : end + 1])
