from io import BytesIO
import wave

from fastapi.testclient import TestClient

from main import app


def _wav_bytes() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


client = TestClient(app)


def test_missing_consent_returns_400() -> None:
    response = client.post(
        "/api/v1/transcribe",
        data={
            "patient_id": "PAT-12345",
            "patient_consent": "false",
            "consent_timestamp": "2026-03-26T10:33:00Z",
        },
        files={"audio": ("sample.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "consent_error"
