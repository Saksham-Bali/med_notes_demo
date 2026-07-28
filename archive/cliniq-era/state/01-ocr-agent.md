# Agent 01: OCR Agent

> **Status:** EXISTS — needs upgrades  
> **Deployment:** Standalone microservice  
> **Port:** `5001`  
> **Base URL:** `http://ocr-agent:5001`

---

## 1. What This Agent Does

The OCR Agent is the **first touch point** for any handwritten or scanned document entering the platform. It takes raw images (scanned notes, photographed prescriptions, printed reports) and converts them into clean, structured text. It does NOT interpret the text — it only extracts it. Interpretation is the job of downstream agents.

---

## 2. Current State (What Already Exists)

You already have a working OCR pipeline using Gemini Vision API that:
- Accepts images of handwritten clinical notes
- Extracts text using Gemini 2.5 Pro Vision
- Performs basic layout analysis
- Returns raw extracted text

This was demonstrated in the Phase 1 SOAP Extraction Pipeline.

---

## 3. What Needs to Change

### 3.1 Add Indic Script Support (Sarvam Vision)

**Why:** TMC patients and some clinicians write in Hindi, Marathi, Tamil, and other Indian languages. Gemini Vision is optimized for English handwriting. Sarvam Vision (3B parameter model) is purpose-built for Indian script document understanding.

**How:**

```
Input Image
    │
    ▼
┌─────────────────────┐
│  Language Detector   │  ◄── Sarvam Detect Language API
│  (on image text)     │      OR heuristic: script detection
└────────┬────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 English    Indic
    │         │
    ▼         ▼
 Gemini    Sarvam
 Vision    Vision
    │         │
    └────┬────┘
         │
         ▼
  Unified Text Output
```

**Implementation:**

```python
# Add to your existing OCR service

import httpx

class OCRAgent:
    def __init__(self):
        self.gemini_client = GeminiVisionClient()  # your existing client
        self.sarvam_client = SarvamVisionClient()
        self.lang_detector = SarvamLanguageDetector()

    async def extract(self, image_bytes: bytes, metadata: dict) -> OCRResult:
        # Step 1: Detect script type
        script_type = await self.lang_detector.detect_script(image_bytes)
        
        # Step 2: Route to appropriate OCR engine
        if script_type in ["devanagari", "tamil", "telugu", "bengali", "gujarati", 
                           "kannada", "malayalam", "odia", "punjabi", "urdu"]:
            raw_text = await self.sarvam_client.extract(image_bytes)
            engine_used = "sarvam_vision"
        else:
            raw_text = await self.gemini_client.extract(image_bytes)
            engine_used = "gemini_vision"
        
        # Step 3: Post-processing (common for both engines)
        cleaned_text = self._post_process(raw_text)
        
        return OCRResult(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            script_detected=script_type,
            engine_used=engine_used,
            confidence=self._compute_confidence(raw_text),
            layout_regions=self._extract_layout(raw_text),
        )
```

### 3.2 Add Layout-Aware Extraction

**Why:** Clinical notes have structure — headings, sections, tables, signatures. Current extraction flattens everything. Downstream agents (especially SOAP Extractor) need to know what's a heading vs body text vs table.

**How:**

```python
class LayoutRegion:
    type: str          # "heading" | "body" | "table" | "signature" | "date" | "annotation"
    text: str          # extracted text for this region
    bounding_box: dict # {x, y, width, height} in normalized coords
    confidence: float  # OCR confidence for this region
    order: int         # reading order position
```

### 3.3 Add Confidence Scoring Per Region

**Why:** Some parts of handwritten notes are clear, others are illegible. Downstream agents need to know which parts to trust and which to flag as uncertain.

**How:** Both Gemini and Sarvam return confidence metrics. Normalize them to a 0-1 scale and attach to each layout region. If any region's confidence < 0.5, flag it as `needs_human_review`.

---

## 4. API Contract

### 4.1 Endpoint

```
POST /api/v1/extract
Content-Type: multipart/form-data
```

### 4.2 Request

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | file | Yes | Image file (PNG, JPG, TIFF, PDF page) |
| `patient_id` | string | Yes | Patient identifier for provenance |
| `source_type` | string | Yes | `"handwritten"` or `"printed"` or `"scanned"` |
| `language_hint` | string | No | ISO language code hint (e.g., `"hi"`, `"en"`) |
| `department` | string | No | Originating department |

### 4.3 Response

```json
{
  "agent_id": "ocr-agent",
  "patient_id": "PAT-12345",
  "timestamp": "2026-03-26T10:30:00Z",
  "result": {
    "full_text": "Patient complains of persistent cough for 2 weeks...",
    "script_detected": "latin",
    "engine_used": "gemini_vision",
    "overall_confidence": 0.87,
    "layout_regions": [
      {
        "type": "heading",
        "text": "Chief Complaint",
        "confidence": 0.95,
        "order": 1,
        "bounding_box": {"x": 0.05, "y": 0.02, "w": 0.4, "h": 0.05}
      },
      {
        "type": "body",
        "text": "Patient complains of persistent cough for 2 weeks...",
        "confidence": 0.87,
        "order": 2,
        "bounding_box": {"x": 0.05, "y": 0.08, "w": 0.9, "h": 0.25}
      }
    ],
    "flags": {
      "low_confidence_regions": [3],
      "needs_human_review": false
    }
  },
  "metadata": {
    "processing_time_ms": 2340,
    "image_dimensions": {"width": 2480, "height": 3508}
  },
  "errors": []
}
```

---

## 5. Deployment

### 5.1 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]
```

### 5.2 Environment Variables

```env
GEMINI_API_KEY=your-gemini-api-key
SARVAM_API_KEY=your-sarvam-api-key
SARVAM_VISION_ENDPOINT=https://api.sarvam.ai/v1/vision
SARVAM_DETECT_LANG_ENDPOINT=https://api.sarvam.ai/v1/detect-language
OCR_DEFAULT_ENGINE=gemini         # fallback if detection fails
OCR_CONFIDENCE_THRESHOLD=0.5      # below this = needs_human_review
LOG_LEVEL=INFO
```

### 5.3 Health Check

```
GET /health → { "status": "ok", "engines": {"gemini": true, "sarvam": true} }
```

---

## 6. How the Orchestrator Calls This Agent

```python
# In the main orchestrator / router
async def process_handwritten_note(image_bytes, patient_id, department):
    ocr_result = await http_client.post(
        "http://ocr-agent:5001/api/v1/extract",
        files={"image": image_bytes},
        data={
            "patient_id": patient_id,
            "source_type": "handwritten",
            "department": department,
        }
    )
    
    # Pass OCR result to SOAP Extractor
    soap_result = await http_client.post(
        "http://soap-extractor:5002/api/v1/extract",
        json={
            "text": ocr_result["result"]["full_text"],
            "layout_regions": ocr_result["result"]["layout_regions"],
            "patient_id": patient_id,
            "source_confidence": ocr_result["result"]["overall_confidence"],
        }
    )
```

---

## 7. Testing Checklist

- [ ] English handwritten note → Gemini Vision → correct text extraction
- [ ] Hindi handwritten note → Sarvam Vision → correct Devanagari extraction
- [ ] Mixed Hindi-English note → correct engine routing per region
- [ ] Low-quality scan → confidence < threshold → `needs_human_review` flagged
- [ ] PDF page input → converted to image → extraction works
- [ ] Layout regions correctly identify headings vs body vs tables
- [ ] API returns within 5 seconds for single-page image
- [ ] Sarvam API down → fallback to Gemini with warning in response
- [ ] Health endpoint reports engine availability correctly

---

## 8. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | ≥0.104 | HTTP framework |
| `uvicorn` | ≥0.24 | ASGI server |
| `httpx` | ≥0.25 | Async HTTP client for Sarvam/Gemini APIs |
| `google-generativeai` | ≥0.3 | Gemini Vision SDK |
| `Pillow` | ≥10.0 | Image preprocessing |
| `pdf2image` | ≥1.16 | PDF page to image conversion |
| `python-multipart` | ≥0.0.6 | File upload handling |

---

## 9. File Structure

```
ocr-agent/
├── main.py                  # FastAPI app, routes
├── agents/
│   ├── gemini_ocr.py        # Gemini Vision wrapper
│   ├── sarvam_ocr.py        # Sarvam Vision wrapper
│   └── language_detector.py # Script/language detection
├── models/
│   ├── request.py           # Request schemas
│   └── response.py          # Response schemas (OCRResult, LayoutRegion)
├── utils/
│   ├── image_preprocessing.py  # Resize, deskew, contrast
│   └── post_processing.py      # Text cleanup, whitespace normalization
├── config.py                # Environment variable loading
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_gemini.py
    ├── test_sarvam.py
    └── test_routing.py
```
