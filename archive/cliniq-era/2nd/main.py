import logging
from datetime import UTC, datetime
from functools import lru_cache
from time import perf_counter

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from agents import (
    SarvamSpeechClient,
    SarvamTextTranslationClient,
    build_transcript_body,
    choose_original_mode,
    is_code_mixed_text,
    normalize_language_hint,
    primary_language_code,
    transcript_to_text,
    validate_consent,
)
from config import Settings, get_settings
from errors import AudioValidationError, FallbackUnavailableError, ProviderError, VoiceTranscriptionError
from fallback import GoogleSpeechToTextClient, GoogleTranslateClient
from models import (
    ErrorDetail,
    ProviderTranscript,
    TranscriptBody,
    TranscriptSegment,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptionResult,
)
from models.response import ResponseMetadata
from utils import assess_audio_quality, cleanup_file, persist_upload_file


class TranscriptionService:
    def __init__(
        self,
        settings: Settings,
        *,
        speech_client: SarvamSpeechClient | None = None,
        translation_client: SarvamTextTranslationClient | None = None,
        google_stt_client: GoogleSpeechToTextClient | None = None,
        google_translate_client: GoogleTranslateClient | None = None,
    ):
        self.settings = settings
        self.speech_client = speech_client or SarvamSpeechClient(settings)
        self.translation_client = translation_client or SarvamTextTranslationClient(settings)
        self.google_stt_client = google_stt_client or GoogleSpeechToTextClient()
        self.google_translate_client = google_translate_client or GoogleTranslateClient()

    async def process(self, request: TranscriptionRequest, upload_file: UploadFile) -> TranscriptionResponse:
        started = perf_counter()
        stored_audio = await persist_upload_file(upload_file)
        engines_used: list[str] = []
        fallback_used = False
        used_batch_api = False

        try:
            validate_consent(request, consent_required=self.settings.consent_required)
            if stored_audio.duration_seconds and stored_audio.duration_seconds > self.settings.max_audio_duration_seconds:
                raise AudioValidationError(
                    f"Audio duration exceeds the maximum allowed length of {self.settings.max_audio_duration_seconds} seconds."
                )

            audio_quality = assess_audio_quality(stored_audio.path, stored_audio.duration_seconds)
            normalized_hint = normalize_language_hint(request.language_hint)
            prefer_batch = bool(
                self.settings.use_batch_for_long_audio
                and stored_audio.duration_seconds
                and stored_audio.duration_seconds > self.settings.sarvam_batch_threshold_seconds
            )
            original_mode = choose_original_mode(normalized_hint, self.settings.sarvam_non_english_mode)

            try:
                original_provider = await self.speech_client.transcribe(
                    audio_path=stored_audio.path,
                    language_code=normalized_hint or "unknown",
                    mode=original_mode,
                    input_audio_codec=stored_audio.input_audio_codec,
                    prefer_batch=prefer_batch,
                )
                engines_used.append(original_provider.engine)
                used_batch_api = used_batch_api or original_provider.used_batch_api
            except ProviderError:
                if not self.settings.enable_google_fallback:
                    raise
                original_provider = await self.google_stt_client.transcribe(
                    audio_path=stored_audio.path,
                    language_code=normalized_hint or "en-IN",
                )
                engines_used.append(original_provider.engine)
                fallback_used = True

            detected_language = original_provider.language_code or normalized_hint or "unknown"
            detected_primary = primary_language_code(detected_language) or "unknown"
            original_transcript = build_transcript_body(
                text=original_provider.transcript,
                language=detected_primary,
                duration_seconds=stored_audio.duration_seconds,
                timestamps=original_provider.timestamps,
                diarized_transcript=original_provider.diarized_transcript,
                confidence=original_provider.language_probability,
            )

            english_transcript, english_engine, english_used_batch, english_fallback_used = await self._build_english_transcript(
                original_provider=original_provider,
                original_transcript=original_transcript,
                stored_audio=stored_audio,
                detected_language=detected_language,
                prefer_batch=prefer_batch,
            )
            if english_engine:
                engines_used.append(english_engine)
            used_batch_api = used_batch_api or english_used_batch
            fallback_used = fallback_used or english_fallback_used

            result = TranscriptionResult(
                language_detected=detected_primary,
                language_confidence=original_provider.language_probability,
                is_code_mixed=is_code_mixed_text(original_provider.transcript) or original_mode == "codemix",
                transcript_original=original_transcript,
                transcript_english=english_transcript,
                full_text_english=transcript_to_text(english_transcript),
                audio_quality=audio_quality,
            )
            metadata = ResponseMetadata(
                audio_duration_seconds=stored_audio.duration_seconds,
                processing_time_ms=int((perf_counter() - started) * 1000),
                engines_used=engines_used,
                consent_verified=True,
                used_batch_api=used_batch_api,
                fallback_used=fallback_used,
            )
            return TranscriptionResponse(
                agent_id=self.settings.service_name,
                patient_id=request.patient_id,
                timestamp=datetime.now(UTC),
                result=result,
                metadata=metadata,
                errors=[],
            )
        finally:
            cleanup_file(stored_audio.path)

    async def _build_english_transcript(
        self,
        *,
        original_provider: ProviderTranscript,
        original_transcript: TranscriptBody,
        stored_audio,
        detected_language: str,
        prefer_batch: bool,
    ) -> tuple[TranscriptBody, str | None, bool, bool]:
        if primary_language_code(detected_language) == "en":
            return TranscriptBody(language="en", segments=original_transcript.segments), None, False, False

        try:
            english_provider = await self.speech_client.transcribe(
                audio_path=stored_audio.path,
                language_code=detected_language,
                mode="translate",
                input_audio_codec=stored_audio.input_audio_codec,
                prefer_batch=prefer_batch,
            )
            english_transcript = build_transcript_body(
                text=english_provider.transcript,
                language="en",
                duration_seconds=stored_audio.duration_seconds,
                timestamps=english_provider.timestamps,
                diarized_transcript=english_provider.diarized_transcript,
                confidence=english_provider.language_probability,
            )
            return english_transcript, english_provider.engine, english_provider.used_batch_api, False
        except ProviderError:
            pass

        try:
            translated_segments: list[TranscriptSegment] = []
            for segment in original_transcript.segments:
                translated_text = await self.translation_client.translate_text(
                    text=segment.text,
                    source_language_code=detected_language,
                    target_language_code="en-IN",
                )
                translated_segments.append(
                    TranscriptSegment(
                        speaker=segment.speaker,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        text=translated_text,
                        confidence=segment.confidence,
                    )
                )
            return TranscriptBody(language="en", segments=translated_segments), "sarvam_translate_v1", False, True
        except ProviderError:
            if not self.settings.enable_google_fallback:
                raise

        translated_segments = []
        for segment in original_transcript.segments:
            translated_text = await self.google_translate_client.translate_text(
                text=segment.text,
                source_language_code=detected_language,
                target_language_code="en",
            )
            translated_segments.append(
                TranscriptSegment(
                    speaker=segment.speaker,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    text=translated_text,
                    confidence=segment.confidence,
                )
            )
        return TranscriptBody(language="en", segments=translated_segments), "google_translate", False, True


@lru_cache
def get_service() -> TranscriptionService:
    return TranscriptionService(get_settings())


settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(settings.service_name)

app = FastAPI(title="Voice Transcription Agent", version="1.0.0")


@app.exception_handler(VoiceTranscriptionError)
async def voice_transcription_exception_handler(_, exc: VoiceTranscriptionError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(FallbackUnavailableError)
async def fallback_exception_handler(_, exc: FallbackUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    patient_id: str = Form(...),
    patient_consent: bool = Form(...),
    consent_timestamp: datetime = Form(...),
    language_hint: str | None = Form(default=None),
    session_type: str | None = Form(default=None),
    department: str | None = Form(default=None),
    service: TranscriptionService = Depends(get_service),
) -> TranscriptionResponse:
    try:
        request = TranscriptionRequest(
            patient_id=patient_id,
            patient_consent=patient_consent,
            consent_timestamp=consent_timestamp,
            language_hint=language_hint,
            session_type=session_type,
            department=department,
        )
        return await service.process(request, audio)
    except HTTPException:
        raise
    except VoiceTranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected transcription failure")
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(code="internal_server_error", message=str(exc)).model_dump(),
        ) from exc
