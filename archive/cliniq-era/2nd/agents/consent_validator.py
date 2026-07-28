from models.request import TranscriptionRequest

from errors import ConsentError


def validate_consent(request: TranscriptionRequest, *, consent_required: bool = True) -> None:
    if consent_required and not request.patient_consent:
        raise ConsentError("Patient consent flag is missing. Cannot process audio without explicit consent.")
    if request.consent_timestamp is None:
        raise ConsentError("Consent timestamp is missing.")
