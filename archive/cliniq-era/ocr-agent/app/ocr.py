import base64
import os
import re
import time
from openai import OpenAI

from app.config import (
    OPENROUTER_API_KEY,
    OPENAI_BASE_URL,
    LLM_MODEL,
)

OCR_EXTRACTION_PROMPT = """### SYSTEM ROLE
You are an expert OCR (Optical Character Recognition) specialist focused on medical documents.

### INSTRUCTION
Your ONLY task is to transcribe the handwritten text from the medical note image exactly as it appears.

**Critical Rules:**
1. **NO CORRECTIONS**: Do not fix spelling, grammar, or medical terminology errors
2. **NO INTERPRETATION**: Do not try to make sense of ambiguous text
3. **PRESERVE LAYOUT**: Maintain line breaks and spacing where possible
4. **CHARACTER-BY-CHARACTER**: If "l0mg" is written (with lowercase 'L'), write "l0mg" (don't correct to "10mg")
5. **UNCERTAIN TEXT**: If a word is completely illegible, write [ILLEGIBLE] in its place
6. **NO ASSUMPTIONS**: If you see "BP: 12O/8O" (with letter O), write exactly that

### OUTPUT FORMAT
Provide ONLY the raw transcribed text with no additional commentary, explanations, or JSON formatting.

Start the transcription on the next line:
---
"""

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=OPENAI_BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )
    return _client


def extract_text_from_image(image_bytes: bytes, mime_type: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    client = get_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            }
        ],
        max_tokens=4000,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    # Strip leading separator line from prompt format
    cleaned = re.sub(r"^---\n", "", raw)
    cleaned = re.sub(r"\n---$", "", cleaned)
    return cleaned.strip()


def _compute_confidence(text: str) -> tuple[float, int]:
    """Return (confidence_score, illegible_count)."""
    illegible_count = len(re.findall(r"\[ILLEGIBLE\]", text, re.IGNORECASE))
    confidence = 1.0 - (illegible_count * 0.05)
    confidence = max(0.0, min(1.0, confidence))
    return confidence, illegible_count


def _detect_indic_script(text: str) -> bool:
    """Return True if Devanagari Unicode characters are present."""
    return bool(re.search(r"[\u0900-\u097F]", text))


def _split_layout_regions(text: str) -> list[dict]:
    """
    Heuristically split the OCR text into layout regions.
    Lines 1-3 go to 'header', remainder to 'body'.
    """
    lines = text.splitlines()
    header_lines = lines[:3]
    body_lines = lines[3:]
    regions = []
    if header_lines:
        regions.append({"region": "header", "text": "\n".join(header_lines).strip()})
    if body_lines:
        regions.append({"region": "body", "text": "\n".join(body_lines).strip()})
    if not regions:
        regions.append({"region": "body", "text": text})
    return regions


def run_ocr(image_bytes: bytes, mime_type: str) -> dict:
    """
    Run OCR on the supplied image bytes and return the structured result dict.
    """
    start = time.time()
    full_text = extract_text_from_image(image_bytes, mime_type)
    elapsed_ms = int((time.time() - start) * 1000)

    confidence, illegible_count = _compute_confidence(full_text)
    has_indic = _detect_indic_script(full_text)
    needs_review = illegible_count > 3 or confidence < 0.6

    return {
        "full_text": full_text,
        "overall_confidence": round(confidence, 4),
        "layout_regions": _split_layout_regions(full_text),
        "flags": {
            "needs_human_review": needs_review,
            "has_indic_script": has_indic,
            "illegible_count": illegible_count,
        },
        "processing_time_ms": elapsed_ms,
    }
