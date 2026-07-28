from __future__ import annotations

import json
import re
from pathlib import Path

from openai import OpenAI

from config import Settings
from models.counselling_fact import CounsellingFact
from models.request import TranscriptSegment

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "counselling_extraction.txt"
TRANSCRIPT_PLACEHOLDER = "[[TRANSCRIPT]]"


class FactExtractionError(RuntimeError):
    """Raised when the LLM response cannot be turned into structured facts."""


class OpenRouterFactExtractor:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.llm_model
        self._client = OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.openrouter_api_key,
        ) if settings.openrouter_api_key else None
        self._prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    def extract(
        self,
        segments: list[TranscriptSegment],
        full_transcript: str,
    ) -> list[CounsellingFact]:
        if not segments or not full_transcript.strip():
            return []
        if self._client is None:
            raise FactExtractionError("AZURE_API_KEY is not configured.")

        prompt = self._prompt_template.replace(
            TRANSCRIPT_PLACEHOLDER,
            self._format_transcript(segments),
        )
        response = self._client.chat.completions.create(
            model=self.model_name,
            max_tokens=2_000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.choices[0].message.content.strip() if response.choices and response.choices[0].message.content else ""
        items = self._parse_json_array(raw_text)
        facts: list[CounsellingFact] = []
        for item in items:
            if isinstance(item, str) and item.strip().lower() == "unknown":
                continue
            try:
                facts.append(CounsellingFact.model_validate(item))
            except Exception as exc:  # pragma: no cover - defensive against malformed LLM output
                raise FactExtractionError(f"Invalid fact payload returned by model: {item}") from exc
        return facts

    def _format_transcript(self, segments: list[TranscriptSegment]) -> str:
        rendered_segments = []
        for segment in segments:
            rendered_segments.append(
                f"[{segment.start_time:.1f}-{segment.end_time:.1f}] "
                f"{segment.speaker}: {segment.text}"
            )
        return "\n".join(rendered_segments)

    def _parse_json_array(self, raw_text: str) -> list[dict]:
        candidate = raw_text.strip()
        if not candidate:
            return []
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.DOTALL).strip()

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("[")
            end = candidate.rfind("]")
            if start == -1 or end == -1 or end < start:
                raise FactExtractionError("Model response did not contain a JSON array.")
            parsed = json.loads(candidate[start : end + 1])

        if isinstance(parsed, list):
            return parsed
        raise FactExtractionError("Model response was not a JSON array.")
