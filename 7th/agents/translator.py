from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import Settings


@dataclass
class TranslationResult:
    translated_text: str
    source_language_code: str
    target_language_code: str
    model: str
    request_id: str | None = None


def chunk_text(text: str, max_chars: int) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in cleaned.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        paragraph_length = len(paragraph) + 2
        if current and current_length + paragraph_length > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_length = len(paragraph)
            continue

        if len(paragraph) > max_chars:
            sentences = paragraph.split(". ")
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                sentence = sentence if sentence.endswith(".") else f"{sentence}."
                if current and current_length + len(sentence) + 1 > max_chars:
                    chunks.append("\n\n".join(current))
                    current = [sentence]
                    current_length = len(sentence)
                else:
                    current.append(sentence)
                    current_length += len(sentence) + 1
            continue

        current.append(paragraph)
        current_length += paragraph_length

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def get_response_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class Translator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.settings.sarvam_api_key:
            raise RuntimeError("SARVAM_API_KEY is required for translation requests")

        from sarvamai import SarvamAI

        self._client = SarvamAI(
            api_subscription_key=self.settings.sarvam_api_key,
            timeout=self.settings.sarvam_timeout_seconds,
        )
        return self._client

    def translate_text(
        self,
        text: str,
        *,
        source_language_code: str,
        target_language_code: str,
    ) -> TranslationResult:
        client = self._get_client()
        chunks = chunk_text(text, self.settings.translation_max_chars)
        if not chunks:
            raise ValueError("No translatable text was provided")

        translated_chunks: list[str] = []
        detected_source_language = source_language_code
        request_id: str | None = None

        for chunk in chunks:
            response = client.text.translate(
                input=chunk,
                source_language_code=source_language_code,
                target_language_code=target_language_code,
                model=self.settings.sarvam_translation_model,
                numerals_format="international",
            )
            translated_chunks.append(get_response_value(response, "translated_text", ""))
            detected_source_language = get_response_value(
                response,
                "source_language_code",
                detected_source_language,
            )
            request_id = get_response_value(response, "request_id", request_id)

        return TranslationResult(
            translated_text="\n\n".join(chunk for chunk in translated_chunks if chunk),
            source_language_code=detected_source_language,
            target_language_code=target_language_code,
            model=self.settings.sarvam_translation_model,
            request_id=request_id,
        )

