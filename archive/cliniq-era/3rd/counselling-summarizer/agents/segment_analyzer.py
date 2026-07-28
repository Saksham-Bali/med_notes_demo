from __future__ import annotations

from dataclasses import dataclass
from re import Pattern, compile

from models.request import TranscriptSegment

SMALL_TALK_PATTERNS: tuple[Pattern[str], ...] = (
    compile(r"^(hi|hello|good (morning|afternoon|evening)|namaste)[.! ]*$", flags=0),
    compile(r"^(thank you|thanks|okay|ok|alright|bye|goodbye|take care)[.! ]*$", flags=0),
    compile(r"^(how are you|i am fine|i'm fine|doing well)[.! ]*$", flags=0),
)

CLINICAL_KEYWORDS = {
    "afraid",
    "anxious",
    "anxiety",
    "worried",
    "scared",
    "concern",
    "fear",
    "support",
    "cope",
    "coping",
    "counselling",
    "decision",
    "decide",
    "agreed",
    "follow-up",
    "follow up",
    "session",
    "side effect",
    "treatment",
    "chemotherapy",
    "radiation",
    "surgery",
    "hair loss",
    "nausea",
    "family",
    "distressed",
    "upset",
    "overwhelmed",
    "plan",
    "recommend",
    "recommended",
}

EMOTIONAL_KEYWORDS = {
    "afraid",
    "anxious",
    "fear",
    "worried",
    "distressed",
    "upset",
    "overwhelmed",
    "sad",
    "tearful",
    "frustrated",
    "stressed",
}


@dataclass(slots=True)
class SegmentAnalysisResult:
    relevant_segments: list[TranscriptSegment]
    emotional_signal_segments: int


def analyze_segments(segments: list[TranscriptSegment]) -> SegmentAnalysisResult:
    relevant_segments: list[TranscriptSegment] = []
    emotional_signal_segments = 0

    for segment in segments:
        if is_emotional_signal(segment.text):
            emotional_signal_segments += 1

        if is_clinically_relevant(segment):
            relevant_segments.append(segment)

    return SegmentAnalysisResult(
        relevant_segments=relevant_segments,
        emotional_signal_segments=emotional_signal_segments,
    )


def is_clinically_relevant(segment: TranscriptSegment) -> bool:
    text = normalize_text(segment.text)
    if not text:
        return False
    if is_small_talk(text):
        return False
    if any(keyword in text for keyword in CLINICAL_KEYWORDS):
        return True
    if segment.speaker == "doctor" and "?" in segment.text and len(text.split()) >= 4:
        return True
    return len(text.split()) >= 6


def is_emotional_signal(text: str) -> bool:
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in EMOTIONAL_KEYWORDS)


def is_small_talk(text: str) -> bool:
    normalized = normalize_text(text)
    return any(pattern.match(normalized) for pattern in SMALL_TALK_PATTERNS)


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())
