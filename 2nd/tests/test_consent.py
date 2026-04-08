import pytest

from agents.consent_validator import validate_consent
from errors import ConsentError
from models.request import TranscriptionRequest


def test_validate_consent_rejects_missing_flag() -> None:
    request = TranscriptionRequest(
        patient_id="PAT-1",
        patient_consent=False,
        consent_timestamp="2026-03-26T10:33:00Z",
    )

    with pytest.raises(ConsentError):
        validate_consent(request)
