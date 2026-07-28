import json
from pathlib import Path
from types import SimpleNamespace

from agents.fhir_exporter import FHIRExporter
from models.response import GeneratedFiles


def test_fhir_exporter_writes_bundle_with_document_references(tmp_path: Path) -> None:
    settings = SimpleNamespace(output_dir=tmp_path, fhir_version="R4")
    exporter = FHIRExporter(settings)

    output = exporter.export_bundle(
        patient_id="PAT-300",
        patient_name="Ravi Kumar",
        english_text="Patient discharged in stable condition.",
        translated_text="रोगी को स्थिर अवस्था में छुट्टी दी गई।",
        source_language_code="en-IN",
        target_language_code="hi-IN",
        files=GeneratedFiles(
            pdf_english="/outputs/patient_en.pdf",
            pdf_translated="/outputs/patient_hi.pdf",
            audio="/outputs/patient_hi.mp3",
        ),
    )

    bundle = json.loads(Path(output).read_text(encoding="utf-8"))
    assert bundle["resourceType"] == "Bundle"
    resources = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "Patient" in resources
    assert "Composition" in resources
    assert resources.count("DocumentReference") == 3
