import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from mutagen import File as MutagenFile

from errors import AudioValidationError

SUPPORTED_EXTENSIONS = {
    ".aac": "aac",
    ".aiff": "aiff",
    ".amr": "amr",
    ".flac": "flac",
    ".m4a": "x-m4a",
    ".mp3": "mp3",
    ".mp4": "mp4",
    ".ogg": "ogg",
    ".opus": "opus",
    ".wav": "wav",
    ".webm": "webm",
    ".wma": "x-ms-wma",
}


@dataclass(slots=True)
class StoredAudio:
    path: Path
    original_filename: str
    content_type: str | None
    extension: str
    input_audio_codec: str | None
    duration_seconds: float | None
    size_bytes: int


async def persist_upload_file(upload_file: UploadFile) -> StoredAudio:
    suffix = Path(upload_file.filename or "audio.bin").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise AudioValidationError(
            "Unsupported audio format. Supported formats include WAV, MP3, M4A, OGG, AAC, FLAC, AIFF, AMR, WMA, MP4, and WebM."
        )

    content = await upload_file.read()
    if not content:
        raise AudioValidationError("Uploaded audio file is empty.")

    fd, temp_path = tempfile.mkstemp(prefix="voice-audio-", suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)

    path = Path(temp_path)
    duration_seconds = _detect_duration_seconds(path)
    return StoredAudio(
        path=path,
        original_filename=upload_file.filename or path.name,
        content_type=upload_file.content_type,
        extension=suffix,
        input_audio_codec=SUPPORTED_EXTENSIONS[suffix],
        duration_seconds=duration_seconds,
        size_bytes=len(content),
    )


def _detect_duration_seconds(path: Path) -> float | None:
    try:
        metadata = MutagenFile(path)
    except Exception:  # noqa: BLE001
        return None

    if metadata is None or not getattr(metadata, "info", None):
        return None
    length = getattr(metadata.info, "length", None)
    return round(float(length), 3) if length is not None else None


def cleanup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
