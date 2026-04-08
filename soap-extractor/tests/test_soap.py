"""Tests for the soap-extractor service."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("AZURE_API_KEY", "test-key")

from fastapi.testclient import TestClient

SAMPLE_SOAP_JSON = {
    "soap_note": {
        "subjective": {
            "chief_complaint": "Headache for 3 days",
            "hpi": "Patient complains of headache for 3 days, associated with nausea and photophobia.",
            "symptoms": ["Headache", "Nausea", "Photophobia"],
            "patient_history": "Hypertension (HTN)",
        },
        "objective": {
            "vitals": {"bp": "140/90", "hr": "88", "temp": None, "rr": None, "weight": None},
            "physical_exam": {
                "findings": ["Neurological exam: no focal deficits"],
                "text_raw": "Neuro exam: no focal deficits",
            },
            "labs_imaging": "Pending",
        },
        "assessment": {
            "primary_diagnosis": {
                "value": "Migraine",
                "certainty_degree": 0.95,
                "evidence_text": "Dx: Migraine",
            },
            "differential_diagnosis": [],
        },
        "plan": {
            "medications": [
                {"drug": "Sumatriptan", "dosage": "50mg", "sig": "PO PRN", "handwriting_confidence": 0.95},
                {"drug": "Ibuprofen", "dosage": "400mg", "sig": "q6h for 5 days", "handwriting_confidence": 0.95},
            ],
            "procedures_ordered": [],
            "patient_instructions": "Follow-up in 1 week",
        },
    },
    "metadata": {"ocr_quality_check": "Clear and legible", "critical_ambiguities": []},
}

SAMPLE_OCR_TEXT = (
    "Date: 12/5/24. Pt c/o headache x 3 days, nausea, photophobia. "
    "PMHx: HTN. Exam: BP 140/90, HR 88. Neuro exam: no focal deficits. "
    "Dx: Migraine. Rx: Sumatriptan 50mg PO PRN, Ibuprofen 400mg q6h x5d. F/u 1 week."
)


def _make_mock_completion(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [choice]
    return mock_response


class TestHealth(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def test_health_returns_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "soap-extractor")


class TestExtractEndpoint(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def _post_extract(self, ocr_text: str = SAMPLE_OCR_TEXT, soap_json: dict = None) -> dict:
        if soap_json is None:
            soap_json = SAMPLE_SOAP_JSON
        mock_completion = _make_mock_completion(json.dumps(soap_json))

        with patch("app.soap.get_client") as mock_get_client:
            mock_azure_client = MagicMock()
            mock_azure_client.chat.completions.create.return_value = mock_completion
            mock_get_client.return_value = mock_azure_client

            response = self.client.post(
                "/api/v1/extract",
                json={
                    "text": ocr_text,
                    "patient_id": "P001",
                    "department": "neurology",
                    "source_confidence": 0.87,
                    "layout_regions": [],
                },
            )
        return response

    def test_extract_returns_200(self):
        resp = self._post_extract()
        self.assertEqual(resp.status_code, 200)

    def test_extract_result_structure(self):
        resp = self._post_extract()
        body = resp.json()
        self.assertIn("result", body)
        result = body["result"]
        self.assertIn("soap", result)
        self.assertIn("clinical_facts", result)
        self.assertIn("extraction_confidence", result)
        self.assertIn("processing_time_ms", result)

    def test_soap_structure(self):
        resp = self._post_extract()
        soap = resp.json()["result"]["soap"]
        self.assertIn("subjective", soap)
        self.assertIn("objective", soap)
        self.assertIn("assessment", soap)
        self.assertIn("plan", soap)

    def test_soap_subjective_fields(self):
        resp = self._post_extract()
        subjective = resp.json()["result"]["soap"]["subjective"]
        self.assertIn("chief_complaint", subjective)
        self.assertIn("symptoms", subjective)
        self.assertIn("hpi", subjective)
        self.assertIn("patient_history", subjective)

    def test_clinical_facts_generated(self):
        resp = self._post_extract()
        facts = resp.json()["result"]["clinical_facts"]
        self.assertIsInstance(facts, list)
        self.assertGreater(len(facts), 0)

    def test_clinical_facts_contain_diagnosis(self):
        resp = self._post_extract()
        facts = resp.json()["result"]["clinical_facts"]
        diagnoses = [f for f in facts if f["entity_type"] == "diagnosis"]
        self.assertGreater(len(diagnoses), 0)
        primary = diagnoses[0]
        self.assertEqual(primary["entity_name"], "migraine")
        self.assertEqual(primary["patient_id"], "P001")
        self.assertEqual(primary["department"], "neurology")

    def test_clinical_facts_contain_medications(self):
        resp = self._post_extract()
        facts = resp.json()["result"]["clinical_facts"]
        medications = [f for f in facts if f["entity_type"] == "medication"]
        self.assertEqual(len(medications), 2)
        med_names = {m["entity_name"] for m in medications}
        self.assertIn("medication_sumatriptan", med_names)
        self.assertIn("medication_ibuprofen", med_names)

    def test_clinical_fact_has_required_fields(self):
        resp = self._post_extract()
        facts = resp.json()["result"]["clinical_facts"]
        required_fields = {
            "fact_id", "patient_id", "entity_name", "entity_type",
            "certainty", "certainty_label", "is_negated", "source_type",
            "department", "evidence_text", "date", "modality",
        }
        for fact in facts:
            for field in required_fields:
                self.assertIn(field, fact, f"Missing field '{field}' in fact: {fact}")

    def test_extraction_confidence_is_float(self):
        resp = self._post_extract()
        confidence = resp.json()["result"]["extraction_confidence"]
        self.assertIsInstance(confidence, float)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_empty_text_returns_400(self):
        with patch("app.soap.get_client"):
            resp = self.client.post(
                "/api/v1/extract",
                json={"text": "   ", "patient_id": "P001"},
            )
        self.assertEqual(resp.status_code, 400)

    def test_missing_text_returns_422(self):
        resp = self.client.post(
            "/api/v1/extract",
            json={"patient_id": "P001"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_missing_patient_id_returns_422(self):
        resp = self.client.post(
            "/api/v1/extract",
            json={"text": "Some text"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_markdown_json_response_is_parsed(self):
        """LLM sometimes wraps JSON in ```json ... ``` blocks."""
        wrapped = "```json\n" + json.dumps(SAMPLE_SOAP_JSON) + "\n```"
        mock_completion = _make_mock_completion(wrapped)

        with patch("app.soap.get_client") as mock_get_client:
            mock_azure_client = MagicMock()
            mock_azure_client.chat.completions.create.return_value = mock_completion
            mock_get_client.return_value = mock_azure_client

            resp = self.client.post(
                "/api/v1/extract",
                json={"text": SAMPLE_OCR_TEXT, "patient_id": "P001"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("result", resp.json())

    def test_source_confidence_factored_into_extraction_confidence(self):
        resp = self._post_extract(soap_json=SAMPLE_SOAP_JSON)
        # source_confidence=0.87, primary_dx certainty=0.95, two meds=0.95
        # avg = (0.87 + 0.95 + 0.95 + 0.95) / 4 = 0.93
        confidence = resp.json()["result"]["extraction_confidence"]
        self.assertAlmostEqual(confidence, 0.93, places=2)

    def test_optional_department_defaults_to_none(self):
        soap_json = SAMPLE_SOAP_JSON
        mock_completion = _make_mock_completion(json.dumps(soap_json))

        with patch("app.soap.get_client") as mock_get_client:
            mock_azure_client = MagicMock()
            mock_azure_client.chat.completions.create.return_value = mock_completion
            mock_get_client.return_value = mock_azure_client

            resp = self.client.post(
                "/api/v1/extract",
                json={"text": SAMPLE_OCR_TEXT, "patient_id": "P002"},
            )
        self.assertEqual(resp.status_code, 200)
        facts = resp.json()["result"]["clinical_facts"]
        for fact in facts:
            self.assertIsNone(fact["department"])


class TestSoapModule(unittest.TestCase):
    """Unit tests for individual soap module functions."""

    def test_parse_json_from_response_raw_json(self):
        from app.soap import parse_json_from_response
        raw = json.dumps({"key": "value"})
        result = parse_json_from_response(raw)
        self.assertEqual(result["key"], "value")

    def test_parse_json_from_response_markdown_block(self):
        from app.soap import parse_json_from_response
        raw = "```json\n{\"key\": \"value\"}\n```"
        result = parse_json_from_response(raw)
        self.assertEqual(result["key"], "value")

    def test_parse_json_from_response_no_json_raises(self):
        from app.soap import parse_json_from_response
        with self.assertRaises(ValueError):
            parse_json_from_response("This is not JSON at all.")

    def test_soap_to_clinical_facts_primary_dx(self):
        from app.soap import soap_to_clinical_facts
        soap = {
            "soap_note": {
                "assessment": {
                    "primary_diagnosis": {
                        "value": "Migraine",
                        "certainty_degree": 0.95,
                        "evidence_text": "Dx: Migraine",
                    },
                    "differential_diagnosis": [],
                },
                "plan": {"medications": []},
            }
        }
        facts = soap_to_clinical_facts(soap, "P001", "neurology")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["entity_name"], "migraine")
        self.assertEqual(facts[0]["entity_type"], "diagnosis")
        self.assertEqual(facts[0]["certainty_label"], "confirmed")

    def test_soap_to_clinical_facts_suspected_dx(self):
        from app.soap import soap_to_clinical_facts
        soap = {
            "soap_note": {
                "assessment": {
                    "primary_diagnosis": {
                        "value": "URI",
                        "certainty_degree": 0.6,
                        "evidence_text": "Dx: ?URI",
                    },
                    "differential_diagnosis": [],
                },
                "plan": {"medications": []},
            }
        }
        facts = soap_to_clinical_facts(soap, "P001", None)
        self.assertEqual(facts[0]["certainty_label"], "suspected")

    def test_soap_to_clinical_facts_unknown_dx_skipped(self):
        from app.soap import soap_to_clinical_facts
        soap = {
            "soap_note": {
                "assessment": {
                    "primary_diagnosis": {"value": "Unknown", "certainty_degree": 0.0, "evidence_text": ""},
                    "differential_diagnosis": [],
                },
                "plan": {"medications": []},
            }
        }
        facts = soap_to_clinical_facts(soap, "P001", None)
        self.assertEqual(len(facts), 0)

    def test_soap_to_clinical_facts_medications(self):
        from app.soap import soap_to_clinical_facts
        soap = {
            "soap_note": {
                "assessment": {
                    "primary_diagnosis": {"value": "Unknown"},
                    "differential_diagnosis": [],
                },
                "plan": {
                    "medications": [
                        {"drug": "Metformin", "dosage": "500mg", "sig": "BID", "handwriting_confidence": 0.95}
                    ]
                },
            }
        }
        facts = soap_to_clinical_facts(soap, "P001", "endocrinology")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["entity_type"], "medication")
        self.assertEqual(facts[0]["entity_name"], "medication_metformin")
        self.assertEqual(facts[0]["certainty"], 0.99)

    def test_soap_to_clinical_facts_differential_dx(self):
        from app.soap import soap_to_clinical_facts
        soap = {
            "soap_note": {
                "assessment": {
                    "primary_diagnosis": {"value": "Unknown"},
                    "differential_diagnosis": ["Tension Headache", "Cluster Headache"],
                },
                "plan": {"medications": []},
            }
        }
        facts = soap_to_clinical_facts(soap, "P001", None)
        self.assertEqual(len(facts), 2)
        for f in facts:
            self.assertEqual(f["certainty_label"], "suspected")
            self.assertEqual(f["certainty"], 0.5)

    def test_fact_ids_are_unique_uuids(self):
        from app.soap import soap_to_clinical_facts
        soap = {
            "soap_note": {
                "assessment": {
                    "primary_diagnosis": {
                        "value": "Migraine",
                        "certainty_degree": 0.95,
                        "evidence_text": "Dx: Migraine",
                    },
                    "differential_diagnosis": ["Tension Headache"],
                },
                "plan": {
                    "medications": [
                        {"drug": "Sumatriptan", "dosage": "50mg", "sig": "PRN", "handwriting_confidence": 0.9}
                    ]
                },
            }
        }
        facts = soap_to_clinical_facts(soap, "P001", "neurology")
        fact_ids = [f["fact_id"] for f in facts]
        self.assertEqual(len(fact_ids), len(set(fact_ids)), "fact_ids must be unique")


if __name__ == "__main__":
    unittest.main()
