from __future__ import annotations

import json
import re
from pathlib import Path

from openai import AzureOpenAI

from config import Settings
from models.bullet_point import BulletPoint
from models.request import TranscriptSegment

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "transcript_correction.txt"
TRANSCRIPT_PLACEHOLDER = "[[TRANSCRIPT]]"


class TranscriptCorrector:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.azure_deployment
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.azure_api_key,
            api_version=settings.azure_api_version,
        ) if settings.azure_api_key else None
        self._prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    def correct(
        self,
        segments: list[TranscriptSegment],
        full_transcript: str,
    ) -> tuple[str, list[BulletPoint]]:
        """Return (corrected_transcript, bullet_points). Falls back to raw transcript on failure."""
        if not full_transcript.strip() or self._client is None:
            return full_transcript, []

        rendered = self._render_segments(segments)
        prompt = self._prompt_template.replace(TRANSCRIPT_PLACEHOLDER, rendered)
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                max_tokens=2_000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = (
                response.choices[0].message.content.strip()
                if response.choices and response.choices[0].message.content
                else ""
            )
            return self._parse(raw_text, fallback_transcript=full_transcript)
        except Exception:  # noqa: BLE001 — correction is best-effort
            return full_transcript, []

    def _render_segments(self, segments: list[TranscriptSegment]) -> str:
        parts = []
        for seg in segments:
            parts.append(
                f"[{seg.start_time:.1f}-{seg.end_time:.1f}] {seg.speaker}: {seg.text}"
            )
        return "\n".join(parts)

    def _parse(self, raw_text: str, *, fallback_transcript: str) -> tuple[str, list[BulletPoint]]:
        candidate = raw_text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.DOTALL).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1:
                return fallback_transcript, []
            try:
                payload = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                return fallback_transcript, []

        corrected = payload.get("corrected_transcript") or fallback_transcript
        raw_bullets = payload.get("bullet_points") or []
        bullet_points: list[BulletPoint] = []
        for i, item in enumerate(raw_bullets, start=1):
            if not isinstance(item, dict):
                continue
            text = item.get("text", "").strip()
            if not text:
                continue
            bullet_points.append(
                BulletPoint(
                    id=item.get("id") or f"bp-{i}",
                    text=text,
                    source_time_start=item.get("source_time_start"),
                    source_time_end=item.get("source_time_end"),
                )
            )
        return corrected, bullet_points
