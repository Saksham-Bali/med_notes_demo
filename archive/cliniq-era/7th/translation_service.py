from __future__ import annotations

from typing import Any

from agents.fhir_exporter import FHIRExporter
from agents.pdf_generator import PDFGenerator
from agents.translator import TranslationResult, Translator
from agents.tts_generator import TextToSpeechGenerator
from config import Settings, get_settings
from language import (
    is_tts_supported,
    language_name,
    normalize_language_code,
    normalize_translation_language,
)
from models.request import TranslateRequest
from models.response import GeneratedFiles, TranslationPayload, TranslateResponse
from utils import sanitize_filename_component


def prettify_key(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").strip().title()


def render_discharge_summary(summary: Any, *, indent: int = 0) -> str:
    spacer = "  " * indent

    if isinstance(summary, str):
        return summary.strip()

    if isinstance(summary, (int, float, bool)):
        return str(summary)

    if isinstance(summary, list):
        lines: list[str] = []
        for item in summary:
            rendered = render_discharge_summary(item, indent=indent + 1).strip()
            if not rendered:
                continue
            for index, line in enumerate(rendered.splitlines()):
                prefix = f"{spacer}- " if index == 0 else f"{spacer}  "
                lines.append(f"{prefix}{line}")
        return "\n".join(lines)

    if isinstance(summary, dict):
        sections: list[str] = []
        for key, value in summary.items():
            title = prettify_key(str(key))
            rendered = render_discharge_summary(value, indent=indent + 1).strip()
            if not rendered:
                continue

            if "\n" in rendered:
                sections.append(f"{spacer}{title}\n{rendered}")
            else:
                sections.append(f"{spacer}{title}: {rendered}")
        return "\n\n".join(sections)

    return str(summary)

class TranslationService:
    def __init__(
        self,
        settings: Settings | None = None,
        translator: Translator | None = None,
        tts_generator: TextToSpeechGenerator | None = None,
        pdf_generator: PDFGenerator | None = None,
        fhir_exporter: FHIRExporter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.translator = translator or Translator(self.settings)
        self.tts_generator = tts_generator or TextToSpeechGenerator(self.settings)
        self.pdf_generator = pdf_generator or PDFGenerator(self.settings)
        self.fhir_exporter = fhir_exporter or FHIRExporter(self.settings)

    def process_request(self, request: TranslateRequest) -> TranslateResponse:
        source_language = normalize_language_code(request.source_language or self.settings.default_source_language)
        target_language = normalize_translation_language(request.target_language)
        english_text = render_discharge_summary(request.discharge_summary).strip()
        if not english_text:
            raise ValueError("discharge_summary must contain renderable text")

        translation = self.translator.translate_text(
            english_text,
            source_language_code=source_language,
            target_language_code=target_language,
        )

        files = GeneratedFiles()
        warnings: list[str] = []
        patient_stub = sanitize_filename_component(request.patient_id)
        patient_name = request.patient_name or self._extract_patient_name(request.discharge_summary)

        if request.generate_pdf:
            files.pdf_english = str(
                self.pdf_generator.generate_pdf(
                    patient_id=request.patient_id,
                    patient_name=patient_name,
                    language_code=source_language,
                    language_label=language_name(source_language),
                    summary_text=english_text,
                    filename=f"{patient_stub}_discharge_en.pdf",
                )
            )
            files.pdf_translated = str(
                self.pdf_generator.generate_pdf(
                    patient_id=request.patient_id,
                    patient_name=patient_name,
                    language_code=target_language,
                    language_label=language_name(target_language),
                    summary_text=translation.translated_text,
                    filename=f"{patient_stub}_discharge_{target_language.split('-', maxsplit=1)[0].lower()}.pdf",
                )
            )

        if request.generate_audio:
            if is_tts_supported(target_language):
                files.audio = str(
                    self.tts_generator.generate_audio(
                        patient_id=request.patient_id,
                        text=translation.translated_text,
                        target_language_code=target_language,
                    )
                )
            else:
                warnings.append(
                    f"Audio was skipped because {language_name(target_language)} is not currently supported by {self.settings.sarvam_tts_model}."
                )

        if request.generate_fhir:
            files.fhir_bundle = str(
                self.fhir_exporter.export_bundle(
                    patient_id=request.patient_id,
                    patient_name=patient_name,
                    english_text=english_text,
                    translated_text=translation.translated_text,
                    source_language_code=translation.source_language_code,
                    target_language_code=translation.target_language_code,
                    files=files,
                )
            )

        return TranslateResponse(
            result=TranslationPayload(
                translated_text=translation.translated_text,
                source_language=translation.source_language_code,
                target_language=translation.target_language_code,
                translation_model=translation.model,
                files=files,
                warnings=warnings,
            )
        )

    def _extract_patient_name(self, discharge_summary: Any) -> str | None:
        if not isinstance(discharge_summary, dict):
            return None

        candidate_keys = ("patient_name", "name", "patient")
        for key in candidate_keys:
            value = discharge_summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested_name = value.get("name")
                if isinstance(nested_name, str) and nested_name.strip():
                    return nested_name.strip()
        return None
