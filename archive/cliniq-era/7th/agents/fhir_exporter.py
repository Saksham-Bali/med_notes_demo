from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from config import Settings
from language import language_name
from models.response import GeneratedFiles
from utils import sanitize_filename_component


class FHIRExporter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def export_bundle(
        self,
        *,
        patient_id: str,
        patient_name: str | None,
        english_text: str,
        translated_text: str,
        source_language_code: str,
        target_language_code: str,
        files: GeneratedFiles,
    ) -> Path:
        bundle = {
            "resourceType": "Bundle",
            "id": str(uuid4()),
            "type": "collection",
            "timestamp": datetime.now(UTC).isoformat(),
            "meta": {"profile": [f"http://hl7.org/fhir/{self.settings.fhir_version}/Bundle"]},
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": patient_id,
                        "identifier": [{"system": "urn:patient-id", "value": patient_id}],
                        "name": [{"text": patient_name or patient_id}],
                    }
                },
                {
                    "resource": {
                        "resourceType": "Composition",
                        "id": str(uuid4()),
                        "status": "final",
                        "type": {"text": "Discharge summary translation package"},
                        "date": datetime.now(UTC).isoformat(),
                        "title": "Translated discharge summary",
                        "section": [
                            {
                                "title": f"English Summary ({language_name(source_language_code)})",
                                "text": {"status": "generated", "div": self._narrative(english_text)},
                            },
                            {
                                "title": f"Translated Summary ({language_name(target_language_code)})",
                                "text": {"status": "generated", "div": self._narrative(translated_text)},
                            },
                        ],
                    }
                },
            ],
        }

        for label, file_path in (
            ("English PDF", files.pdf_english),
            ("Translated PDF", files.pdf_translated),
            ("Audio Narration", files.audio),
        ):
            if not file_path:
                continue
            bundle["entry"].append(
                {
                    "resource": {
                        "resourceType": "DocumentReference",
                        "id": str(uuid4()),
                        "status": "current",
                        "description": label,
                        "subject": {"reference": f"Patient/{patient_id}"},
                        "content": [{"attachment": {"url": file_path, "title": label}}],
                    }
                }
            )

        output_path = self.settings.output_dir / f"{sanitize_filename_component(patient_id)}_discharge.fhir.json"
        output_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path

    def _narrative(self, text: str) -> str:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        return f"<div xmlns=\"http://www.w3.org/1999/xhtml\"><p>{escaped}</p></div>"
