from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import Settings


class PDFGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.environment = Environment(
            loader=FileSystemLoader(str(settings.pdf_template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate_pdf(
        self,
        *,
        patient_id: str,
        patient_name: str | None,
        language_code: str,
        language_label: str,
        summary_text: str,
        filename: str,
    ) -> Path:
        html = self._render_html(
            patient_id=patient_id,
            patient_name=patient_name,
            language_code=language_code,
            language_label=language_label,
            summary_text=summary_text,
        )
        output_path = self.settings.output_dir / filename
        self._write_pdf(html, output_path)
        return output_path

    def _render_html(
        self,
        *,
        patient_id: str,
        patient_name: str | None,
        language_code: str,
        language_label: str,
        summary_text: str,
    ) -> str:
        template = self.environment.get_template("discharge_pdf.html")
        return template.render(
            patient_id=patient_id,
            patient_name=patient_name,
            language_code=language_code,
            language_label=language_label,
            summary_text=summary_text,
        )

    def _write_pdf(self, html: str, output_path: Path) -> None:
        from weasyprint import HTML

        HTML(string=html, base_url=str(self.settings.pdf_template_dir.resolve())).write_pdf(str(output_path))

