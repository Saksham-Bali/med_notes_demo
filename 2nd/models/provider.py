from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProviderTranscript:
    transcript: str
    language_code: str | None
    language_probability: float | None
    timestamps: dict[str, Any] | None
    diarized_transcript: dict[str, Any] | None
    engine: str
    used_batch_api: bool = False
