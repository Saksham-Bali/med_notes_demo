from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    speaker: str = "unknown"
    start_time: float = 0.0
    end_time: float = 0.0
    text: str
    confidence: float | None = None


class TranscriptBody(BaseModel):
    language: str
    segments: list[TranscriptSegment] = Field(default_factory=list)


class AudioQuality(BaseModel):
    overall: str
    noise_level: str
    speech_clarity: float | None = None
    clipping_detected: bool | None = None
    silent_ratio: float | None = None
