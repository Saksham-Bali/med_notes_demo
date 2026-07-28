"""Tests for the ocr-agent service."""
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure AZURE_API_KEY is set before importing modules that read it at import time
os.environ.setdefault("AZURE_API_KEY", "test-key")

from fastapi.testclient import TestClient


def _make_mock_completion(content: str) -> MagicMock:
    """Build a mock openai ChatCompletion object that returns `content`."""
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
        self.assertEqual(body["service"], "ocr-agent")


class TestExtractEndpoint(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def _post_image(self, content: str = "Patient complains of chest pain.") -> dict:
        mock_completion = _make_mock_completion(content)
        with patch("app.ocr.get_client") as mock_get_client:
            mock_azure_client = MagicMock()
            mock_azure_client.chat.completions.create.return_value = mock_completion
            mock_get_client.return_value = mock_azure_client

            image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # Minimal JPEG-like bytes
            response = self.client.post(
                "/api/v1/extract",
                data={"patient_id": "P001", "department": "cardiology", "source_type": "handwritten"},
                files={"image": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
            )
        return response

    def test_extract_returns_200(self):
        resp = self._post_image()
        self.assertEqual(resp.status_code, 200)

    def test_extract_result_structure(self):
        resp = self._post_image("Patient complains of chest pain.")
        body = resp.json()
        self.assertIn("result", body)
        result = body["result"]
        self.assertIn("full_text", result)
        self.assertIn("overall_confidence", result)
        self.assertIn("layout_regions", result)
        self.assertIn("flags", result)
        self.assertIn("processing_time_ms", result)

    def test_extract_full_text_content(self):
        resp = self._post_image("Patient complains of chest pain.")
        body = resp.json()
        self.assertIn("chest pain", body["result"]["full_text"])

    def test_confidence_is_float_between_0_and_1(self):
        resp = self._post_image("Normal text without illegible parts.")
        confidence = resp.json()["result"]["overall_confidence"]
        self.assertIsInstance(confidence, float)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_illegible_markers_reduce_confidence(self):
        # 4 [ILLEGIBLE] markers → confidence = 1.0 - 4*0.05 = 0.8, needs_human_review False
        # 5 [ILLEGIBLE] markers → confidence = 0.75, needs_human_review True (count > 3)
        text_with_illegible = "BP [ILLEGIBLE] HR [ILLEGIBLE] Temp [ILLEGIBLE] RR [ILLEGIBLE] Wt [ILLEGIBLE]"
        resp = self._post_image(text_with_illegible)
        result = resp.json()["result"]
        self.assertEqual(result["flags"]["illegible_count"], 5)
        self.assertTrue(result["flags"]["needs_human_review"])
        self.assertAlmostEqual(result["overall_confidence"], 0.75)

    def test_indic_script_detection(self):
        # Include a Devanagari character (U+0905 = अ)
        resp = self._post_image("Patient name: \u0905\u0928\u0941")
        result = resp.json()["result"]
        self.assertTrue(result["flags"]["has_indic_script"])

    def test_no_indic_script_in_latin_text(self):
        resp = self._post_image("Patient complains of chest pain.")
        result = resp.json()["result"]
        self.assertFalse(result["flags"]["has_indic_script"])

    def test_extract_missing_image_returns_422(self):
        response = self.client.post(
            "/api/v1/extract",
            data={"patient_id": "P001"},
        )
        self.assertEqual(response.status_code, 422)

    def test_extract_missing_patient_id_returns_422(self):
        image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        response = self.client.post(
            "/api/v1/extract",
            files={"image": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 422)

    def test_unsupported_mime_type_returns_415(self):
        mock_completion = _make_mock_completion("some text")
        with patch("app.ocr.get_client") as mock_get_client:
            mock_azure_client = MagicMock()
            mock_azure_client.chat.completions.create.return_value = mock_completion
            mock_get_client.return_value = mock_azure_client

            response = self.client.post(
                "/api/v1/extract",
                data={"patient_id": "P001"},
                files={"image": ("test.gif", io.BytesIO(b"GIF89a"), "image/gif")},
            )
        self.assertEqual(response.status_code, 415)

    def test_layout_regions_structure(self):
        text = "Header line 1\nHeader line 2\nHeader line 3\nBody line 1\nBody line 2"
        resp = self._post_image(text)
        regions = resp.json()["result"]["layout_regions"]
        self.assertIsInstance(regions, list)
        self.assertGreater(len(regions), 0)
        for region in regions:
            self.assertIn("region", region)
            self.assertIn("text", region)


class TestOcrModule(unittest.TestCase):
    """Unit tests for the ocr module functions directly."""

    def test_compute_confidence_no_illegible(self):
        from app.ocr import _compute_confidence
        confidence, count = _compute_confidence("Normal clear text.")
        self.assertEqual(count, 0)
        self.assertAlmostEqual(confidence, 1.0)

    def test_compute_confidence_with_illegible(self):
        from app.ocr import _compute_confidence
        text = "[ILLEGIBLE] some text [ILLEGIBLE]"
        confidence, count = _compute_confidence(text)
        self.assertEqual(count, 2)
        self.assertAlmostEqual(confidence, 0.9)

    def test_compute_confidence_floor_at_zero(self):
        from app.ocr import _compute_confidence
        # 25 illegible markers would push below 0
        text = " ".join(["[ILLEGIBLE]"] * 25)
        confidence, count = _compute_confidence(text)
        self.assertEqual(count, 25)
        self.assertAlmostEqual(confidence, 0.0)

    def test_detect_indic_script_true(self):
        from app.ocr import _detect_indic_script
        self.assertTrue(_detect_indic_script("Hello \u0905"))

    def test_detect_indic_script_false(self):
        from app.ocr import _detect_indic_script
        self.assertFalse(_detect_indic_script("Hello world"))

    def test_split_layout_regions_short_text(self):
        from app.ocr import _split_layout_regions
        regions = _split_layout_regions("Line 1\nLine 2")
        # Both lines go to header (only 2 lines, <=3)
        self.assertTrue(any(r["region"] == "header" for r in regions))

    def test_split_layout_regions_long_text(self):
        from app.ocr import _split_layout_regions
        text = "\n".join([f"Line {i}" for i in range(10)])
        regions = _split_layout_regions(text)
        region_names = {r["region"] for r in regions}
        self.assertIn("header", region_names)
        self.assertIn("body", region_names)


if __name__ == "__main__":
    unittest.main()
