from datetime import datetime

from pydantic import BaseModel, Field

from .transcript import AudioQuality, TranscriptBody


class ErrorDetail(BaseModel):
    code: str
    message: str


class TranscriptionResult(BaseModel):
    language_detected: str | None = None
    language_confidence: float | None = None
    is_code_mixed: bool = False
    transcript_original: TranscriptBody
    transcript_english: TranscriptBody
    full_text_english: str
    audio_quality: AudioQuality


class ResponseMetadata(BaseModel):
    audio_duration_seconds: float | None = None
    processing_time_ms: int
    engines_used: list[str] = Field(default_factory=list)
    consent_verified: bool
    used_batch_api: bool = False
    fallback_used: bool = False


class TranscriptionResponse(BaseModel):
    agent_id: str
    patient_id: str
    timestamp: datetime
    result: TranscriptionResult
    metadata: ResponseMetadata
    errors: list[ErrorDetail] = Field(default_factory=list)
