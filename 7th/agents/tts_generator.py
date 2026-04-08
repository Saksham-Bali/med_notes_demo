from __future__ import annotations

import base64
import io
import wave
from pathlib import Path
from typing import Any

from config import Settings
from language import language_file_suffix
from utils import sanitize_filename_component


def get_response_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class TextToSpeechGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.settings.sarvam_api_key:
            raise RuntimeError("SARVAM_API_KEY is required for audio generation")

        from sarvamai import SarvamAI

        self._client = SarvamAI(
            api_subscription_key=self.settings.sarvam_api_key,
            timeout=self.settings.sarvam_timeout_seconds,
        )
        return self._client

    def generate_audio(
        self,
        *,
        patient_id: str,
        text: str,
        target_language_code: str,
    ) -> Path:
        client = self._get_client()
        audio_payload = text.strip()
        if len(audio_payload) > self.settings.tts_max_chars:
            raise ValueError(
                f"Translated text exceeds the {self.settings.tts_max_chars}-character limit for {self.settings.sarvam_tts_model}. "
                "Retry with generate_audio=false or shorten the summary."
            )
        request_kwargs = {
            "text": audio_payload,
            "target_language_code": target_language_code,
            "model": self.settings.sarvam_tts_model,
            "output_audio_codec": self.settings.sarvam_output_audio_codec,
        }
        if self.settings.sarvam_tts_speaker:
            request_kwargs["speaker"] = self.settings.sarvam_tts_speaker

        response = client.text_to_speech.convert(**request_kwargs)

        audios = get_response_value(response, "audios", [])
        if isinstance(audios, str):
            audios = [audios]
        if not audios:
            raise RuntimeError("Sarvam TTS did not return any audio payloads")

        output_extension = self.settings.sarvam_output_audio_codec.lower()
        output_path = self.settings.output_dir / (
            f"{sanitize_filename_component(patient_id)}_discharge_{language_file_suffix(target_language_code)}.{output_extension}"
        )

        decoded_payloads = [base64.b64decode(item) for item in audios]
        output_path.write_bytes(self._merge_audio(decoded_payloads, output_extension))
        return output_path

    def _merge_audio(self, payloads: list[bytes], codec: str) -> bytes:
        if len(payloads) == 1:
            return payloads[0]

        if codec != "wav":
            return b"".join(payloads)

        output_buffer = io.BytesIO()
        with wave.open(output_buffer, "wb") as merged:
            first = wave.open(io.BytesIO(payloads[0]), "rb")
            try:
                merged.setnchannels(first.getnchannels())
                merged.setsampwidth(first.getsampwidth())
                merged.setframerate(first.getframerate())
                merged.writeframes(first.readframes(first.getnframes()))
            finally:
                first.close()

            for payload in payloads[1:]:
                segment = wave.open(io.BytesIO(payload), "rb")
                try:
                    merged.writeframes(segment.readframes(segment.getnframes()))
                finally:
                    segment.close()

        return output_buffer.getvalue()
