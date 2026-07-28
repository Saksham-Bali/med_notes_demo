from io import BytesIO
from pathlib import Path
import wave

import pytest
from fastapi.testclient import TestClient

from errors import ProviderError
from main import TranscriptionService, app, get_service
from models import ProviderTranscript


class FailingSpeechClient:
    async def transcribe(self, **kwargs) -> ProviderTranscript:
        mode = kwargs["mode"]
        if mode == "translate":
            raise ProviderError("translate failed")
        return ProviderTranscript(
            transcript="मुझे chemotherapy se dar lag raha hai",
            language_code="hi-IN",
            language_probability=0.91,
            timestamps=None,
            diarized_transcript=None,
            engine="sarvam_saaras_v3",
            used_batch_api=False,
        )


class StubTranslationClient:
    async def translate_text(self, *, text: str, source_language_code: str, target_language_code: str = "en-IN") -> str:
        return "I am afraid of chemotherapy"


class UnusedGoogleStt:
    async def transcribe(self, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("Google STT should not be used")


class UnusedGoogleTranslate:
    async def translate_text(self, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("Google Translate should not be used")


def _wav_bytes() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


@pytest.fixture
def client() -> TestClient:
    service = TranscriptionService(
        settings=get_service().settings.model_copy(update={"enable_google_fallback": False}),
        speech_client=FailingSpeechClient(),
        translation_client=StubTranslationClient(),
        google_stt_client=UnusedGoogleStt(),
        google_translate_client=UnusedGoogleTranslate(),
    )
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_text_translation_fallback_is_used_when_speech_translate_fails(client: TestClient) -> None:
    response = client.post(
        "/api/v1/transcribe",
        data={
            "patient_id": "PAT-12345",
            "patient_consent": "true",
            "consent_timestamp": "2026-03-26T10:33:00Z",
            "language_hint": "hi",
        },
        files={"audio": ("sample.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["transcript_english"]["segments"][0]["text"] == "I am afraid of chemotherapy"
    assert "sarvam_translate_v1" in payload["metadata"]["engines_used"]
    assert payload["metadata"]["fallback_used"] is True
