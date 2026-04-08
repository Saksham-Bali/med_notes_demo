import json
import mimetypes
import tempfile
from pathlib import Path

import httpx
from sarvamai import AsyncSarvamAI

from config import Settings
from errors import ProviderError
from models.provider import ProviderTranscript


class SarvamSpeechClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._batch_client = AsyncSarvamAI(api_subscription_key=settings.sarvam_api_key or "")

    async def transcribe(
        self,
        *,
        audio_path: Path,
        language_code: str | None,
        mode: str,
        input_audio_codec: str | None,
        prefer_batch: bool,
    ) -> ProviderTranscript:
        if not self.settings.sarvam_api_key:
            raise ProviderError("SARVAM_API_KEY is not configured.")

        if prefer_batch:
            return await self._transcribe_with_batch(
                audio_path=audio_path,
                language_code=language_code,
                mode=mode,
            )

        return await self._transcribe_with_rest(
            audio_path=audio_path,
            language_code=language_code,
            mode=mode,
            input_audio_codec=input_audio_codec,
        )

    async def _transcribe_with_rest(
        self,
        *,
        audio_path: Path,
        language_code: str | None,
        mode: str,
        input_audio_codec: str | None,
    ) -> ProviderTranscript:
        mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        data: dict[str, str] = {
            "model": self.settings.sarvam_stt_model,
            "mode": mode,
            "language_code": language_code or "unknown",
            "with_timestamps": "true",
        }
        if input_audio_codec:
            data["input_audio_codec"] = input_audio_codec

        try:
            async with httpx.AsyncClient(
                base_url=self.settings.sarvam_base_url,
                timeout=self.settings.sarvam_request_timeout_seconds,
                headers={"api-subscription-key": self.settings.sarvam_api_key},
            ) as client:
                with audio_path.open("rb") as audio_file:
                    response = await client.post(
                        "/speech-to-text",
                        data=data,
                        files={"file": (audio_path.name, audio_file, mime_type)},
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Sarvam speech-to-text request failed: {exc}") from exc

        payload = response.json()
        return ProviderTranscript(
            transcript=payload.get("transcript", "").strip(),
            language_code=payload.get("language_code"),
            language_probability=payload.get("language_probability"),
            timestamps=payload.get("timestamps"),
            diarized_transcript=payload.get("diarized_transcript"),
            engine="sarvam_saaras_v3",
            used_batch_api=False,
        )

    async def _transcribe_with_batch(
        self,
        *,
        audio_path: Path,
        language_code: str | None,
        mode: str,
    ) -> ProviderTranscript:
        try:
            job = self._batch_client.speech_to_text_job.create_job(
                model=self.settings.sarvam_stt_model,
                mode=mode,
                with_diarization=self.settings.enable_batch_diarization and mode != "translate",
                with_timestamps=True,
                language_code=language_code,
            )
            await job.upload_files([str(audio_path)])
            await job.start()
            status = await job.wait_until_complete(
                poll_interval=self.settings.sarvam_batch_poll_interval_seconds,
                timeout=self.settings.sarvam_batch_timeout_seconds,
            )
            if status.job_state.lower() != "completed":
                raise ProviderError(f"Sarvam batch transcription failed with state '{status.job_state}'.")

            with tempfile.TemporaryDirectory(prefix="sarvam-batch-") as output_dir:
                await job.download_outputs(output_dir)
                output_path = Path(output_dir) / f"{audio_path.name}.json"
                if not output_path.exists():
                    raise ProviderError("Sarvam batch transcription completed without a downloadable output file.")
                payload = json.loads(output_path.read_text())
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"Sarvam batch transcription failed: {exc}") from exc

        return ProviderTranscript(
            transcript=str(payload.get("transcript", "")).strip(),
            language_code=payload.get("language_code"),
            language_probability=payload.get("language_probability"),
            timestamps=payload.get("timestamps"),
            diarized_transcript=payload.get("diarized_transcript"),
            engine="sarvam_saaras_v3_batch",
            used_batch_api=True,
        )
