# Agent 10: Translation Layer

> **Status:** NEW — build from scratch  
> **Deployment:** Standalone microservice  
> **Port:** `5010`  
> **Base URL:** `http://translation-layer:5010`

---

## 1. What This Agent Does

The Translation Layer takes **QA-approved English discharge summaries** and produces:
1. **Translated text** in the patient's preferred Indian language (via Sarvam Mayura)
2. **Audio narration** of the summary in their language (via Sarvam Bulbul TTS)
3. **PDF output** ready for printing or digital delivery

---

## 2. Architecture

```
Approved English Summary (from QA Agent)
        │
        ▼
┌───────────────────────┐
│ Language Selection      │  ◄── Patient's preferred language
│ - From patient record   │      or manual selection
│ - Auto-detect from      │      22 Indian languages supported
│   previous interactions │
└───────────┬───────────┘
            │
       ┌────┴──────────┐
       │               │
       ▼               ▼
┌─────────────┐  ┌──────────────┐
│ Text         │  │ Audio         │
│ Translation  │  │ Generation    │
│ Sarvam       │  │ Sarvam        │
│ Mayura       │  │ Bulbul (TTS)  │
└──────┬──────┘  └──────┬───────┘
       │                │
       ▼                ▼
┌─────────────┐  ┌──────────────┐
│ PDF Gen      │  │ MP3 File      │
│ (WeasyPrint) │  │               │
└──────┬──────┘  └──────┬───────┘
       │                │
       └────────┬───────┘
                ▼
         Output Bundle
         - English PDF (canonical)
         - Translated PDF
         - Audio MP3
         - EMR export (FHIR JSON)
```

---

## 3. API Contract

### 3.1 Translate & Generate

```
POST /api/v1/translate
```

```json
{
  "patient_id": "PAT-12345",
  "discharge_summary": { ... },
  "target_language": "hi",
  "generate_audio": true,
  "generate_pdf": true,
  "generate_fhir": true
}
```

### 3.2 Response

```json
{
  "agent_id": "translation-layer",
  "result": {
    "translated_text": "...",
    "target_language": "hi",
    "files": {
      "pdf_english": "/outputs/PAT-12345_discharge_en.pdf",
      "pdf_translated": "/outputs/PAT-12345_discharge_hi.pdf",
      "audio": "/outputs/PAT-12345_discharge_hi.mp3",
      "fhir_bundle": "/outputs/PAT-12345_discharge.fhir.json"
    }
  }
}
```

---

## 4. Deployment

```env
SARVAM_API_KEY=your-sarvam-api-key
SARVAM_TRANSLATE_ENDPOINT=https://api.sarvam.ai/v1/translate
SARVAM_TTS_ENDPOINT=https://api.sarvam.ai/v1/text-to-speech
SUPPORTED_LANGUAGES=hi,mr,ta,te,bn,gu,kn,ml,pa,or,en
PDF_TEMPLATE_DIR=/templates/pdf
FHIR_VERSION=R4
LOG_LEVEL=INFO
```

---

## 5. File Structure

```
translation-layer/
├── main.py
├── agents/
│   ├── translator.py          # Sarvam Mayura wrapper
│   ├── tts_generator.py       # Sarvam Bulbul wrapper
│   ├── pdf_generator.py       # WeasyPrint PDF generation
│   └── fhir_exporter.py       # HL7 FHIR bundle generation
├── templates/
│   └── discharge_pdf.html     # PDF template
├── models/
│   ├── request.py
│   └── response.py
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_translation.py
    ├── test_pdf.py
    └── test_fhir.py
```
