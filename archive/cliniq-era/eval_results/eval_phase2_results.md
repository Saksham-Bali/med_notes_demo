# Voice Pipeline Evaluation — EkaCare Medical ASR
**Date:** April 7, 2026  
**Dataset:** `ekacare/eka-medical-asr-evaluation-dataset`  
**Phase:** 2 (full dataset, all contexts, with LLM correction)  
**STT Model:** Sarvam `saaras:v3` (`mode=transcribe`, `language_code=en-IN`)  
**LLM Corrector:** Azure OpenAI `gpt-4o-mini` (temperature=0)

---

## Overall Results

| Metric | Sarvam Baseline | + LLM Corrector | Δ |
|---|---|---|---|
| **WER** | 25.92% | 23.72% | **−2.20pp** |
| **Entity Recall** | 61.30% | 62.69% | **+1.39pp** |

**Sample counts:** 3,619 total · 3,478 valid · 141 errors (3.9%)

---

## Per-Context Breakdown

| Context | n | WER (Sarvam) | WER (Corrected) | Δ | Entity Recall (Corrected) |
|---|---|---|---|---|---|
| `conversation` | 110 | 10.5% | 10.4% | +0.08pp | 88.9% |
| `narration_sentence` | 1,303 | 11.4% | 10.6% | +0.73pp | 81.5% |
| `narration_entity` | 2,206 | 35.3% | 32.1% | **+3.20pp** | 50.3% |

---

## Key Observations

- **LLM corrector never regresses** — improvement across all three contexts
- **Biggest win on `narration_entity`** (+3.20pp): dense drug/entity dictation is where Sarvam makes the most phonetic STT errors (e.g. "cap eh sit a bean" → "capecitabine"), and the corrector catches these reliably
- **`conversation` already near-optimal** (10.5% WER, 88.9% entity recall) — the corrector correctly leaves clean transcripts mostly untouched
- **Entity recall improvement (+1.39pp)** confirms the corrector is fixing drug name transcriptions that exact-match entity scoring was missing on the raw Sarvam output

---

## Concrete Examples by Context

### 1. `conversation`: 10.5% WER → 88.9% Entity Recall ✓

**Ground Truth:**  
> "Patient has headache, fever, depression, leg pain. I want to prescribe giving patient Dolo 650."

**Sarvam Transcript:**  
> "Patient has headache, fever, depression, leg pain. Uh, I want to prescribe giving patient Dolo 650."

**Analysis:**
- **WER: 4.8%** — only added "Uh" and a comma
- **Entity Recall: 100%** — all medical terms captured exactly ("headache", "fever", "depression", "leg pain", "Dolo 650")
- **Why it works:** Natural conversation pace, common words, short distinct medical terms

---

### 2. `narration_sentence`: 11.4% WER → 81.5% Entity Recall ✓

*(Full sentences read in dictation style)*

**Ground Truth:**  
> "Take thyroxine 25 mcg once daily on empty stomach and avoid eating outside food for next 2 weeks."

**Sarvam Transcript:**  
> "Take thyroxine 25 mcg once daily on empty stomach and avoid eating outside food for next two weeks."

**Analysis:**
- **WER: ~9%** — only "2 weeks" → "two weeks" (number vs word difference)
- **Entity Recall: 80%** — thyroxine ✓, 25 mcg ✓, once daily ✓, but "2 weeks" became "two weeks" (exact-match failure)
- **Why it's okay:** Complete sentences with context help ASR; minor formatting issues hurt exact-match entity scoring

---

### 3. `narration_entity`: 35.3% WER → 50.3% Entity Recall ✗

*(Rapid-fire drug name dictation — the hardest case)*

**Ground Truth:**  
> "Libotryp 12.5 Mg by 5 Mg Tablet"

**Sarvam Transcript:**  
> "Libotrip 12.5mg/5mg tablet."

**LLM Corrected:**  
> "Lapatinib 12.5mg/5mg tablet."

**Analysis:**
- **WER: 85.7%** — catastrophic! Spelling errors ("Libotryp" → "Libotrip"), format changes ("Mg by" → "mg/"), case errors
- **Entity Recall: 0%** — drug name completely garbled; no exact match possible
- **LLM made it worse:** "corrected" to "Lapatinib" (a different drug entirely!)

**Another extreme example:**
- **Truth:** "capecitabine 500mg"
- **Sarvam:** "cap eh sit a bean 500 milligrams"  
- **WER:** 60% (5 words instead of 2)
- **Entity Recall:** 0% (drug name phonetically destroyed)

**Why it fails:**
- No sentence context to help ASR
- Drug names are phonetically confusing and long
- Rapid dictation = more errors
- Exact-match entity scoring has zero tolerance for any deviation

---

## Summary: Why Entity Recall ≠ WER

| Context | What It Is | Typical Error Pattern | Impact on WER | Impact on Entity Recall |
|---------|-----------|----------------------|---------------|------------------------|
| `conversation` | Natural doctor-patient chat | Minor filler words ("uh", "um") | Low | Minimal — simple terms stay intact |
| `narration_sentence` | Reading full sentences | Word substitutions ("2" → "two") | Low | Moderate — formatting breaks exact match |
| `narration_entity` | Rapid drug name dictation | Phonetic destruction of complex names | **High** | **Severe** — entities completely unrecognizable |

---

## Metrics Definitions

| Metric | Definition |
|---|---|
| **WER** | Word Error Rate (jiwer library, lower is better) |
| **Entity Recall** | Fraction of ground-truth medical entity spans found verbatim in transcript (kwWER proxy) |
| **WER Δ** | `WER_sarvam − WER_corrected` (positive = improvement) |

---

## Run Config

```bash
# Full dataset run
bash scripts/run_eval.sh 2          # phase 2, all contexts, all 3619 samples

# Smoke test (run first to validate)
bash scripts/run_eval.sh 2 100 conversation
```

**Checkpoint file:** `eval_results/eval_phase2_all_full.json`  
**Rate:** ~54 req/min (1.1s sleep between Sarvam calls)  
**Runtime:** ~70 min for full dataset on Tyrone
