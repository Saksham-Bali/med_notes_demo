class VoiceTranscriptionError(Exception):
    status_code = 400
    code = "voice_transcription_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConsentError(VoiceTranscriptionError):
    code = "consent_error"


class AudioValidationError(VoiceTranscriptionError):
    code = "audio_validation_error"


class ProviderError(VoiceTranscriptionError):
    status_code = 502
    code = "provider_error"


class FallbackUnavailableError(ProviderError):
    status_code = 503
    code = "fallback_unavailable"
