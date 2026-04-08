from checks.confidence import check_confidence
from models.response import ClinicalFact


def test_low_confidence_facts_are_reported() -> None:
    facts = [
        ClinicalFact(entity="hepatic lesion", entity_type="finding", certainty=0.45, evidence="CT abdomen"),
        ClinicalFact(entity="pneumonia", entity_type="diagnosis", certainty=0.92, evidence="CXR"),
    ]

    issues = check_confidence(facts, min_confidence=0.6)

    assert len(issues) == 1
    assert issues[0].type == "LOW_CONFIDENCE"
    assert "hepatic lesion" in issues[0].message
