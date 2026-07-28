from pathlib import Path
from types import SimpleNamespace

from agents.pdf_generator import PDFGenerator


def test_pdf_generator_renders_language_metadata(tmp_path: Path, monkeypatch) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "discharge_pdf.html").write_text(
        "Patient={{ patient_id }} Language={{ language_label }} Summary={{ summary_text }}",
        encoding="utf-8",
    )

    settings = SimpleNamespace(pdf_template_dir=template_dir, output_dir=tmp_path)
    generator = PDFGenerator(settings)
    captured: dict[str, str] = {}

    def fake_write_pdf(html: str, output_path: Path) -> None:
        captured["html"] = html
        output_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(generator, "_write_pdf", fake_write_pdf)

    output = generator.generate_pdf(
        patient_id="PAT-200",
        patient_name="Asha",
        language_code="hi-IN",
        language_label="Hindi",
        summary_text="Recovered well.",
        filename="sample.pdf",
    )

    assert output.exists()
    assert "PAT-200" in captured["html"]
    assert "Hindi" in captured["html"]
    assert "Recovered well." in captured["html"]

