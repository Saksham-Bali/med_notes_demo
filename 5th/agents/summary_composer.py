from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config import Settings
from models.discharge_summary import DischargeSummary, SummaryContext
from models.request import GenerateSummaryRequest
from templates import get_template_guidance

if TYPE_CHECKING:
    from openai import AzureOpenAI


class ModelRefusalError(RuntimeError):
    """Raised when the model refuses to produce a structured response."""


class SummaryComposer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AzureOpenAI | None = None
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
        response = client.responses.parse(
            model=self.settings.azure_deployment,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You generate evidence-grounded hospital discharge summaries "
                        "as strictly structured JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text_format=DischargeSummary,
        )

        if response.output_parsed is not None:
            return response.output_parsed

        output = getattr(response, "output", [])
        for item in output:
            for content in getattr(item, "content", []):
                refusal = getattr(content, "refusal", None)
                if refusal:
                    raise ModelRefusalError(refusal)

        if response.output_text:
            return DischargeSummary.model_validate_json(response.output_text)

        raise RuntimeError("The model did not return a discharge summary.")

    def _get_client(self) -> AzureOpenAI:
        if self._client is not None:
            return self._client

        try:
            from openai import AzureOpenAI
            from openai import OpenAIError
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Install dependencies from requirements.txt."
            ) from exc

        try:
            self._client = AzureOpenAI(
                azure_endpoint=self.settings.azure_endpoint,
                api_key=self.settings.azure_api_key,
                api_version=self.settings.azure_api_version,
                timeout=self.settings.openai_timeout,
            )
        except OpenAIError as exc:
            raise RuntimeError(
                "Azure OpenAI client could not be initialized. Set AZURE_API_KEY."
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
            "model_hint": self.settings.azure_deployment,
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
