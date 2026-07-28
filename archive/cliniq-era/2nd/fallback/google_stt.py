from pathlib import Path

from errors import FallbackUnavailableError
from models.provider import ProviderTranscript


class GoogleSpeechToTextClient:
    async def transcribe(self, *, audio_path: Path, language_code: str | None) -> ProviderTranscript:
        try:
            from google.cloud import speech_v1p1beta1 as speech
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise FallbackUnavailableError("Google Speech fallback requires google-cloud-speech.") from exc

        client = speech.SpeechAsyncClient()
        with audio_path.open("rb") as audio_file:
            content = audio_file.read()

        config = speech.RecognitionConfig(
            language_code=language_code or "en-IN",
            enable_automatic_punctuation=True,
        )
        audio = speech.RecognitionAudio(content=content)
        response = await client.recognize(config=config, audio=audio)
        transcript = " ".join(result.alternatives[0].transcript for result in response.results if result.alternatives)

        return ProviderTranscript(
            transcript=transcript.strip(),
            language_code=language_code,
            language_probability=None,
            timestamps=None,
            diarized_transcript=None,
            engine="google_stt",
            used_batch_api=False,
        )
