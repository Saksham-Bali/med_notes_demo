from collections.abc import Iterable

from models.transcript import TranscriptBody, TranscriptSegment


def _normalize_speaker(speaker_id: str | None) -> str:
    if not speaker_id:
        return "unknown"
    return speaker_id.strip().lower().replace(" ", "_")


def _group_timestamp_words(words: list[str], starts: list[float], ends: list[float], confidence: float | None) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    buffer_words: list[str] = []
    buffer_start: float | None = None
    buffer_end: float | None = None

    for index, word in enumerate(words):
        start_time = starts[index]
        end_time = ends[index]
        previous_end = ends[index - 1] if index > 0 else None
        gap = (start_time - previous_end) if previous_end is not None else 0.0

        if buffer_words and (gap > 1.2 or len(buffer_words) >= 20):
            segments.append(
                TranscriptSegment(
                    speaker="unknown",
                    start_time=buffer_start or 0.0,
                    end_time=buffer_end or buffer_start or 0.0,
                    text=" ".join(buffer_words).strip(),
                    confidence=confidence,
                )
            )
            buffer_words = []
            buffer_start = None

        if buffer_start is None:
            buffer_start = start_time
        buffer_end = end_time
        buffer_words.append(word)

        if word.endswith((".", "?", "!")):
            segments.append(
                TranscriptSegment(
                    speaker="unknown",
                    start_time=buffer_start or 0.0,
                    end_time=buffer_end or buffer_start or 0.0,
                    text=" ".join(buffer_words).strip(),
                    confidence=confidence,
                )
            )
            buffer_words = []
            buffer_start = None
            buffer_end = None

    if buffer_words:
        segments.append(
            TranscriptSegment(
                speaker="unknown",
                start_time=buffer_start or 0.0,
                end_time=buffer_end or buffer_start or 0.0,
                text=" ".join(buffer_words).strip(),
                confidence=confidence,
            )
        )

    return [segment for segment in segments if segment.text]


def _segments_from_diarized_entries(entries: Iterable[dict], confidence: float | None) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for entry in entries:
        segments.append(
            TranscriptSegment(
                speaker=_normalize_speaker(entry.get("speaker_id")),
                start_time=float(entry.get("start_time_seconds", 0.0)),
                end_time=float(entry.get("end_time_seconds", entry.get("start_time_seconds", 0.0))),
                text=str(entry.get("transcript", "")).strip(),
                confidence=confidence,
            )
        )
    return [segment for segment in segments if segment.text]


def build_transcript_body(
    *,
    text: str,
    language: str,
    duration_seconds: float | None,
    timestamps: dict | None,
    diarized_transcript: dict | None,
    confidence: float | None,
) -> TranscriptBody:
    if diarized_transcript and diarized_transcript.get("entries"):
        segments = _segments_from_diarized_entries(diarized_transcript["entries"], confidence)
    elif timestamps and timestamps.get("words"):
        words = list(timestamps.get("words") or [])
        starts = list(timestamps.get("start_time_seconds") or [])
        ends = list(timestamps.get("end_time_seconds") or [])
        usable_length = min(len(words), len(starts), len(ends))
        segments = _group_timestamp_words(words[:usable_length], starts[:usable_length], ends[:usable_length], confidence)
    else:
        end_time = float(duration_seconds or 0.0)
        segments = [
            TranscriptSegment(
                speaker="unknown",
                start_time=0.0,
                end_time=end_time,
                text=text.strip(),
                confidence=confidence,
            )
        ]

    return TranscriptBody(language=language, segments=segments)


def transcript_to_text(transcript: TranscriptBody) -> str:
    lines: list[str] = []
    for segment in transcript.segments:
        speaker = segment.speaker.replace("_", " ").title()
        lines.append(f"{speaker}: {segment.text}")
    return "\n".join(lines)
