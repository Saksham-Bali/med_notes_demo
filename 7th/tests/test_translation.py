from pathlib import Path
from types import SimpleNamespace

from language import normalize_language_code
from models.request import TranslateRequest
from translation_service import TranslationService, render_discharge_summary


class FakeTranslator:
    def translate_text(self, text: str, *, source_language_code: str, target_language_code: str):
        return SimpleNamespace(
            translated_text=f"[{target_language_code}] {text}",
            source_language_code=source_language_code,
            target_language_code=target_language_code,
            model="sarvam-translate:v1",
        )


class FakeTTS:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def generate_audio(self, *, patient_id: str, text: str, target_language_code: str) -> Path:
        path = self.output_dir / f"{patient_id}_{target_language_code}.mp3"
        path.write_bytes(b"audio")
        return path


class FakePDF:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def generate_pdf(self, **kwargs) -> Path:
        path = self.output_dir / kwargs["filename"]
        path.write_bytes(b"%PDF-1.4")
        return path


class FakeFHIR:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def export_bundle(self, **kwargs) -> Path:
        path = self.output_dir / "bundle.json"
        path.write_text("{}", encoding="utf-8")
        return path


def make_service(tmp_path: Path) -> TranslationService:
    settings = SimpleNamespace(
        default_source_language="en-IN",
        sarvam_tts_model="bulbul:v3",
    )
    return TranslationService(
        settings=settings,
        translator=FakeTranslator(),
        tts_generator=FakeTTS(tmp_path),
        pdf_generator=FakePDF(tmp_path),
        fhir_exporter=FakeFHIR(tmp_path),
    )


def test_normalize_language_code_supports_short_aliases() -> None:
    assert normalize_language_code("hi") == "hi-IN"
    assert normalize_language_code("od") == "od-IN"
    assert normalize_language_code("ta-IN") == "ta-IN"


def test_render_discharge_summary_formats_nested_content() -> None:
    rendered = render_discharge_summary(
        {
            "diagnosis": "Viral fever",
            "medications": ["Paracetamol", "ORS"],
            "follow_up": {"date": "2026-03-30", "department": "General Medicine"},
        }
    )
    assert "Diagnosis: Viral fever" in rendered
    assert "- Paracetamol" in rendered
    assert "Follow Up" in rendered


def test_process_request_skips_audio_for_non_tts_languages(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    response = service.process_request(
        TranslateRequest(
            patient_id="PAT-100",
            discharge_summary="Stable at discharge.",
            target_language="ur",
        )
    )
    assert response.result.target_language == "ur-IN"
    assert response.result.files.audio is None
    assert response.result.warnings

