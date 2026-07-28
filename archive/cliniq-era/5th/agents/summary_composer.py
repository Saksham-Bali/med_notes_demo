from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from config import Settings
from models.request import GenerateSummaryRequest
from models.discharge_summary import DischargeSummary, SummaryContext
from templates import get_template_guidance
from openai import OpenAI


class ModelRefusalError(RuntimeError):
    """Raised when the model produces an invalid response."""


class SummaryComposer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None
        self._prompt_template = Path("prompts/summary_generation.txt").read_text(
            encoding="utf-8"
        )

    async def compose_summary(
        self,
        request: GenerateSummaryRequest,
        context: SummaryContext,
    ) -> DischargeSummary:
        return await asyncio.to_thread(self._compose_sync, request, context)

    def _compose_sync(
        self,
        request: GenerateSummaryRequest,
        context: SummaryContext,
    ) -> DischargeSummary:
        client = self._get_client()
        prompt = self._build_prompt(request, context)

        response = client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0,
            response_format={"type": "json_object"},
            timeout=self.settings.openai_timeout,
        )

        content = response.choices[0].message.content
        if not content:
            raise ModelRefusalError("The model returned empty content.")

        try:
            return DischargeSummary.model_validate_json(content)
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse discharge summary from model response: {e}"
            ) from e

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI as OpenAIClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Install dependencies from requirements.txt."
            ) from exc

        try:
            self._client = OpenAIClient(
                base_url=self.settings.openai_base_url,
                api_key=self.settings.openrouter_api_key,
                timeout=self.settings.openai_timeout,
            )
        except Exception as exc:
            raise RuntimeError(
                "OpenAI client could not be initialized. Set OPENROUTER_API_KEY."
            ) from exc

        return self._client

    def _build_prompt(
        self,
        request: GenerateSummaryRequest,
        context: SummaryContext,
    ) -> str:
        template_name = request.template or self.settings.default_template
        template_guidance = get_template_guidance(template_name)

        request_context = {
            "patient_id": request.patient_id,
            "admission_date": request.admission_date,
            "discharge_date": request.discharge_date,
            "attending_physician": request.attending_physician,
            "department": request.department,
            "approved_counselling_fact_ids": request.approved_counselling_fact_ids,
            "include_recist": request.include_recist,
            "template": template_name,
            "model_hint": self.settings.llm_model,
        }

        return self._prompt_template.format(
            template_name=template_name,
            template_guidance=template_guidance,
            request_context_json=self._dump_json(request_context),
            patient_state_json=self._dump_json(context.patient_state),
            recist_data_json=self._dump_json(context.recist_data),
            counselling_facts_json=self._dump_json(context.counselling_facts),
        )

    def _dump_json(self, payload: Any) -> str:
        return json.dumps(payload, indent=2, sort_keys=True, default=str)
