from agents.guardrails import validate_counselling_facts
from models.counselling_fact import CounsellingFact


def test_evidence_linking_reduces_certainty_when_excerpt_is_missing() -> None:
    facts = [
        CounsellingFact(
            fact="Patient expressed worry about treatment side effects",
            category="CONCERN",
            certainty=0.8,
            evidence_start_time=10.0,
            evidence_end_time=12.0,
            evidence_text="This sentence is not in the transcript",
            speaker="patient",
        ),
        CounsellingFact(
            fact="Patient seemed unsure about future visits",
            category="FOLLOW_UP",
            certainty=0.5,
            evidence_start_time=15.0,
            evidence_end_time=19.0,
            evidence_text="Another missing quote",
            speaker="patient",
        ),
    ]

    validated = validate_counselling_facts(
        facts=facts,
        transcript="Doctor: Let's discuss your concerns.\nPatient: I am worried about the side effects.",
        min_certainty_threshold=0.3,
        diagnosis_filter_enabled=True,
    )

    assert len(validated) == 1
    assert validated[0].certainty == 0.4
    assert "evidence_not_found_in_transcript" in validated[0].validation_flags
