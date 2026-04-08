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
