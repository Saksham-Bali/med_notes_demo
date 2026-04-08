# Agent 04: Voice Transcription Agent

> **Status:** NEW — build from scratch  
> **Deployment:** Standalone microservice  
> **Port:** `5004`  
> **Base URL:** `http://voice-transcription:5004`

---

## 1. What This Agent Does

The Voice Transcription Agent converts **audio recordings of clinical counselling sessions** into **timestamped English transcripts**. It handles multilingual and code-mixed speech (Hindi-English, Marathi-English, etc.) using Sarvam AI's speech pipeline.

This agent does NOT interpret or summarize the audio — it only transcribes and translates. The Counselling Summarizer (Agent 05) handles interpretation.

---

## 2. Why This Exists

Dr. Bhawesh Pangaria at TMC recommended incorporating vocal counselling sessions into structured documentation. Patients in Indian hospitals speak many languages, often mixing Hindi and English mid-sentence. Standard English-only ASR systems fail on this input. Sarvam AI's Saaras v3 is purpose-built for this exact scenario.

---

## 3. Architecture

```
Audio File (WAV/MP3/M4A)
        │
        ▼
┌───────────────────────┐
│ Step 1: Validate       │  ◄── Check consent flag, audio quality
│ - Consent flag check   │      Reject if no consent metadata
│ - Audio quality check  │
│ - Format normalization │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Step 2: Language Detect │  ◄── Sarvam Detect Language API
│ - Identify spoken       │      Returns: language code + confidence
│   language(s)           │      Detects code-mixing
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Step 3: Transcribe     │  ◄── Sarvam Saaras v3
│ - ASR in detected lang │      Mode: "transcribe" for same-lang
│ - Code-mix mode for    │      Mode: "codemix" for Hindi-English
│   mixed speech          │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Step 4: Translate      │  ◄── Sarvam Mayura (if not English)
│ - Translate transcript  │      Preserves clinical terminology
│   to English canonical  │      Retains original alongside
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Step 5: Speaker        │  ◄── Diarization (identify speakers)
│ Diarization            │      Label: "Doctor" vs "Patient"
│ (optional, if model    │
│  supports it)          │
└───────────┬───────────┘
            │
            ▼
  Timestamped English Transcript
  + Original Language Transcript
```

---

## 4. Implementation Details

### 4.1 Sarvam API Integration

```python
import httpx

class SarvamSpeechClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sarvam.ai/v1"
    
    async def detect_language(self, audio_bytes: bytes) -> LanguageDetection:
        """Detect spoken language in audio."""
        response = await httpx.AsyncClient().post(
            f"{self.base_url}/detect-language",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"audio": audio_bytes},
        )
        data = response.json()
        return LanguageDetection(
            language_code=data["language"],
            confidence=data["confidence"],
            is_code_mixed=data.get("is_code_mixed", False),
        )
    
    async def transcribe(self, audio_bytes: bytes, language: str, mode: str = "transcribe") -> Transcript:
        """Transcribe audio using Saaras v3.
        
        Args:
            mode: "transcribe" = same language output
                  "translate" = English output
                  "codemix" = handle mixed language input
        """
        response = await httpx.AsyncClient().post(
            f"{self.base_url}/speech-to-text",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"audio": audio_bytes},
            data={
                "model": "saaras-v3",
                "language": language,
                "mode": mode,
                "timestamps": True,
                "speaker_diarization": True,
            },
        )
        return self._parse_transcript(response.json())
    
    async def translate_text(self, text: str, source_lang: str, target_lang: str = "en") -> str:
        """Translate text using Mayura."""
        response = await httpx.AsyncClient().post(
            f"{self.base_url}/translate",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "text": text,
                "source_language": source_lang,
                "target_language": target_lang,
                "model": "mayura",
            },
        )
        return response.json()["translated_text"]
```

### 4.2 Consent Validation

**Critical:** Audio recording of counselling sessions requires explicit patient consent. The agent MUST reject any audio that doesn't have consent metadata.

```python
async def validate_consent(metadata: dict) -> bool:
    if not metadata.get("patient_consent"):
        raise ConsentError("Patient consent flag is missing. Cannot process audio without explicit consent.")
    if not metadata.get("consent_timestamp"):
        raise ConsentError("Consent timestamp is missing.")
    return True
```

### 4.3 Fallback Strategy

If Sarvam APIs are unavailable:

```python
async def transcribe_with_fallback(audio_bytes, language):
    try:
        return await sarvam_client.transcribe(audio_bytes, language)
    except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
        logger.warning(f"Sarvam API unavailable: {e}. Falling back to Google Cloud STT.")
        return await google_stt_client.transcribe(audio_bytes, language)
```

---

## 5. API Contract

### 5.1 Endpoint

```
POST /api/v1/transcribe
Content-Type: multipart/form-data
```

### 5.2 Request

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | Yes | Audio file (WAV, MP3, M4A, OGG) |
| `patient_id` | string | Yes | Patient identifier |
| `patient_consent` | boolean | Yes | Explicit consent flag (must be `true`) |
| `consent_timestamp` | string | Yes | ISO timestamp of when consent was given |
| `language_hint` | string | No | Expected language (e.g., `"hi"`, `"mr"`, `"ta"`) |
| `session_type` | string | No | `"counselling"`, `"consultation"`, `"follow_up"` |
| `department` | string | No | Originating department |

### 5.3 Response

```json
{
  "agent_id": "voice-transcription",
  "patient_id": "PAT-12345",
  "timestamp": "2026-03-26T10:33:00Z",
  "result": {
    "language_detected": "hi",
    "is_code_mixed": true,
    "transcript_original": {
      "language": "hi",
      "segments": [
        {
          "speaker": "doctor",
          "start_time": 0.0,
          "end_time": 5.2,
          "text": "Aapko treatment ke baare mein kuch concerns hain?",
          "confidence": 0.91
        },
        {
          "speaker": "patient",
          "start_time": 5.8,
          "end_time": 12.4,
          "text": "Haan doctor, mujhe chemotherapy ke side effects se bahut dar lag raha hai",
          "confidence": 0.88
        }
      ]
    },
    "transcript_english": {
      "segments": [
        {
          "speaker": "doctor",
          "start_time": 0.0,
          "end_time": 5.2,
          "text": "Do you have any concerns about the treatment?",
          "confidence": 0.91
        },
        {
          "speaker": "patient",
          "start_time": 5.8,
          "end_time": 12.4,
          "text": "Yes doctor, I am very afraid of the side effects of chemotherapy",
          "confidence": 0.88
        }
      ]
    },
    "full_text_english": "Doctor: Do you have any concerns about the treatment?\nPatient: Yes doctor, I am very afraid of the side effects of chemotherapy",
    "audio_quality": {
      "overall": "good",
      "noise_level": "low",
      "speech_clarity": 0.89
    }
  },
  "metadata": {
    "audio_duration_seconds": 342,
    "processing_time_ms": 8500,
    "engines_used": ["sarvam_saaras_v3", "sarvam_mayura"],
    "consent_verified": true
  },
  "errors": []
}
```

---

## 6. Deployment

### 6.1 Environment Variables

```env
SARVAM_API_KEY=your-sarvam-api-key
SARVAM_STT_ENDPOINT=https://api.sarvam.ai/v1/speech-to-text
SARVAM_TRANSLATE_ENDPOINT=https://api.sarvam.ai/v1/translate
SARVAM_DETECT_LANG_ENDPOINT=https://api.sarvam.ai/v1/detect-language
GOOGLE_STT_CREDENTIALS=/secrets/google-stt.json    # fallback
GOOGLE_TRANSLATE_CREDENTIALS=/secrets/google-tl.json # fallback
MAX_AUDIO_DURATION_SECONDS=3600     # 1 hour max
CONSENT_REQUIRED=true               # NEVER set to false in production
LOG_LEVEL=INFO
```

---

## 7. Testing Checklist

- [ ] Hindi audio → Saaras v3 transcription → correct Hindi text
- [ ] Hindi audio → Mayura translation → correct English text
- [ ] Code-mixed Hindi-English → codemix mode → handles switches correctly
- [ ] Tamil audio → language detected as "ta" → Saaras transcription works
- [ ] No consent flag → request rejected with 400 error
- [ ] Poor audio quality → quality flag in response, reduced confidence scores
- [ ] Audio > 1 hour → rejected with appropriate error
- [ ] Sarvam API timeout → fallback to Google STT with warning
- [ ] Speaker diarization → doctor vs patient segments labeled
- [ ] Both original and English transcripts present in response

---

## 8. File Structure

```
voice-transcription/
├── main.py
├── agents/
│   ├── consent_validator.py
│   ├── language_detector.py
│   ├── transcriber.py           # Sarvam Saaras v3 wrapper
│   ├── translator.py            # Sarvam Mayura wrapper  
│   └── diarizer.py              # Speaker diarization
├── fallback/
│   ├── google_stt.py            # Google Cloud STT fallback
│   └── google_translate.py      # Google Translate fallback
├── models/
│   ├── request.py
│   ├── response.py
│   └── transcript.py
├── utils/
│   ├── audio_preprocessing.py   # Format conversion, noise detection
│   └── quality_check.py         # Audio quality assessment
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_hindi_transcription.py
    ├── test_codemix.py
    ├── test_consent.py
    └── test_fallback.py
```
