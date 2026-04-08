from agents.guardrails import validate_counselling_facts
from models.counselling_fact import CounsellingFact


def test_guardrails_filter_diagnosis_content() -> None:
    facts = [
        CounsellingFact(
            fact="Patient was diagnosed with breast cancer and discussed the diagnosis",
            category="CONCERN",
            certainty=0.9,
            evidence_start_time=12.0,
            evidence_end_time=18.0,
            evidence_text="I was diagnosed with breast cancer last week",
            speaker="patient",
        ),
        CounsellingFact(
            fact="Patient appeared distressed when discussing the upcoming treatment",
            category="EMOTIONAL",
            certainty=0.82,
            evidence_start_time=20.0,
            evidence_end_time=26.0,
            evidence_text="I feel very overwhelmed about what is coming next",
            speaker="patient",
        ),
    ]

    validated = validate_counselling_facts(
        facts=facts,
        transcript=(
            "Patient: I was diagnosed with breast cancer last week.\n"
            "Patient: I feel very overwhelmed about what is coming next."
        ),
        min_certainty_threshold=0.3,
        diagnosis_filter_enabled=True,
    )

    assert len(validated) == 1
    assert validated[0].category == "EMOTIONAL"
    assert validated[0].fact == "Patient appeared distressed when discussing the upcoming treatment"
