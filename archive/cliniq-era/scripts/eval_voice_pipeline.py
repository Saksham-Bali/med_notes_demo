#!/usr/bin/env python3
"""
Voice Pipeline Evaluation — EkaCare Medical ASR Dataset
========================================================
Tests Sarvam saaras:v3 STT accuracy and (optionally) TranscriptCorrector
LLM correction quality against ground-truth medical transcripts.

Phase 1  — STT only:   measures Sarvam WER, entity recall
Phase 2  — STT + LLM:  measures post-correction WER delta

Dataset : ekacare/eka-medical-asr-evaluation-dataset (HuggingFace)
Metrics : WER, entity_recall (kwWER proxy), wer_delta (Phase 2)

Requirements (not in platform venv — installed by run_eval.sh):
    pip install jiwer datasets huggingface_hub soundfile

Usage:
    # Phase 1 only (STT accuracy)
    python scripts/eval_voice_pipeline.py --phase 1 --max-samples 100

    # Phase 1 + 2 (STT + LLM correction delta)
    python scripts/eval_voice_pipeline.py --phase 2 --max-samples 100

    # Full dataset (takes ~2h)
    python scripts/eval_voice_pipeline.py --phase 2

    # Conversations only (most meaningful for TranscriptCorrector)
    python scripts/eval_voice_pipeline.py --phase 2 --context conversation
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

try:
    from jiwer import wer as compute_wer
except ImportError:
    sys.exit("Run: pip install jiwer")

try:
    from datasets import load_dataset, Audio
except ImportError:
    sys.exit("Run: pip install datasets huggingface_hub")

# ---------------------------------------------------------------------------
# Config — reads from environment (same vars as the platform)
# ---------------------------------------------------------------------------
SARVAM_API_KEY   = os.environ.get("SARVAM_API_KEY", "")
SARVAM_BASE_URL  = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai")
SARVAM_MODEL     = "saaras:v3"
SARVAM_MODE      = "transcribe"  # correct for English; auto-detects would add latency
SARVAM_LANG_CODE = "en-IN"       # explicit → skips language detection overhead

AZURE_API_KEY    = os.environ.get("AZURE_API_KEY", "")
AZURE_ENDPOINT   = os.environ.get("AZURE_ENDPOINT", "").rstrip("/")
AZURE_DEPLOYMENT = os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini")
AZURE_API_VER    = os.environ.get("AZURE_API_VERSION", "2025-01-01-preview")

SCRIPT_DIR   = Path(__file__).parent
REPO_ROOT    = SCRIPT_DIR.parent
PROMPT_FILE  = REPO_ROOT / "3rd/counselling-summarizer/prompts/transcript_correction.txt"
RESULTS_DIR  = REPO_ROOT / "eval_results"

# Rate limiting — 60 req/min confirmed from dashboard (screenshot).
# 1.1s sleep = ~54 req/min, leaving headroom for API call latency overhead.
SARVAM_SLEEP_S = 1.1   # ~54 req/min
LLM_SLEEP_S    = 0.5   # ~120 req/min, gpt-4o-mini is generous

# Checkpoint: flush to disk every N samples so a crash wastes at most N * ~2.5s
CHECKPOINT_EVERY = 10

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class SampleResult:
    sample_id: str
    reference: str
    sarvam_transcript: str
    corrected_transcript: str | None
    medical_entities: list[str]           # entity text strings from ground truth
    wer_sarvam: float                     # WER before correction
    wer_corrected: float | None           # WER after correction (Phase 2 only)
    entity_recall_sarvam: float           # fraction of medical entities found in sarvam output
    entity_recall_corrected: float | None # fraction found after correction
    recording_context: str                # "conversation" / "narrated" / "demonstration"
    type_concept: str                     # "drugs" / "misc_medical" / etc.
    sarvam_latency_s: float
    llm_latency_s: float | None
    error: str | None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation for WER comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _entity_recall(entities: list[str], transcript: str) -> float:
    """
    Fraction of ground-truth medical entities that appear (case-insensitive)
    in the transcript.  This is the kwWER proxy — 1.0 means all entities
    were transcribed correctly.
    """
    if not entities:
        return 1.0
    norm_t = _normalise(transcript)
    found = sum(1 for e in entities if _normalise(e) in norm_t)
    return found / len(entities)


def _parse_medical_entities(raw: Any) -> list[str]:
    """
    Parse the medical_entities field from the dataset.
    Format: [["azithromycin", "drugs", [[4, 16]]], ...]
    Returns list of entity text strings.
    """
    if not raw:
        return []
    try:
        if isinstance(raw, str):
            parsed = ast.literal_eval(raw)
        else:
            parsed = raw
        return [item[0] for item in parsed if isinstance(item, (list, tuple)) and item]
    except Exception:
        return []


def _audio_bytes_to_wav(audio_dict: dict) -> bytes:
    """
    With Audio(decode=False), HuggingFace gives {"bytes": b"...", "path": str}.
    We send the raw bytes directly — Sarvam accepts m4a/mp3/wav etc.
    If bytes are absent (local path only), read from path.
    """
    raw = audio_dict.get("bytes")
    if raw:
        return raw

    path = audio_dict.get("path")
    if path and Path(path).exists():
        return Path(path).read_bytes()

    raise ValueError(f"No audio bytes or accessible path in sample: {audio_dict.get('path')}")


# ---------------------------------------------------------------------------
# Sarvam STT call
# ---------------------------------------------------------------------------

def call_sarvam(audio_bytes: bytes, filename: str = "audio.wav") -> tuple[str, float]:
    """
    Returns (transcript, latency_seconds).
    Retries up to 4 times on 429 with exponential backoff (30s, 60s, 120s, 240s).
    Raises on persistent failure or non-429 HTTP errors.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY not set")

    backoff_delays = [30, 60, 120, 240]  # seconds to wait after each 429
    t0 = time.monotonic()

    for attempt, backoff in enumerate([0] + backoff_delays):
        if backoff:
            print(f"    [429] rate limited — waiting {backoff}s before retry {attempt}/{len(backoff_delays)}...")
            time.sleep(backoff)

        try:
            with httpx.Client(
                base_url=SARVAM_BASE_URL,
                timeout=120.0,
                headers={"api-subscription-key": SARVAM_API_KEY},
            ) as client:
                resp = client.post(
                    "/speech-to-text",
                    data={
                        "model":         SARVAM_MODEL,
                        "mode":          SARVAM_MODE,
                        "language_code": SARVAM_LANG_CODE,
                    },
                    files={"file": (filename, audio_bytes, "audio/wav")},
                )

            if resp.status_code == 429:
                if attempt < len(backoff_delays):
                    continue  # try again with next backoff
                raise RuntimeError(f"Sarvam 429 persisted after {len(backoff_delays)} retries")

            resp.raise_for_status()
            latency = time.monotonic() - t0
            return resp.json().get("transcript", "").strip(), latency

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < len(backoff_delays):
                continue
            raise RuntimeError(f"Sarvam HTTP error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Sarvam request failed: {exc}") from exc

    raise RuntimeError("Sarvam call failed after all retries")


# ---------------------------------------------------------------------------
# TranscriptCorrector (inline, no service dependency)
# ---------------------------------------------------------------------------

def _load_correction_prompt() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Correction prompt not found: {PROMPT_FILE}")
    return PROMPT_FILE.read_text()


def call_corrector(raw_transcript: str) -> tuple[str, float]:
    """
    Calls gpt-4o-mini via Azure to correct the Sarvam transcript.
    For eval purposes we pass a single 'segment' with no timestamps.
    Returns (corrected_transcript, latency_seconds).
    """
    if not AZURE_API_KEY or not AZURE_ENDPOINT:
        raise RuntimeError("AZURE_API_KEY / AZURE_ENDPOINT not set — skipping Phase 2")

    try:
        from openai import AzureOpenAI
    except ImportError:
        raise RuntimeError("openai package not installed")

    prompt_template = _load_correction_prompt()
    # Format as a single segment with no timestamps — realistic for a short clip
    segment_text = f"[0.0-999.0] speaker: {raw_transcript}"
    prompt = prompt_template.replace("[[TRANSCRIPT]]", segment_text)

    client = AzureOpenAI(
        api_key=AZURE_API_KEY,
        azure_endpoint=AZURE_ENDPOINT,
        api_version=AZURE_API_VER,
    )

    t0 = time.monotonic()
    response = client.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0,
    )
    latency = time.monotonic() - t0

    raw_text = response.choices[0].message.content or ""

    # Parse corrected_transcript out of the JSON response
    try:
        # Strip markdown fencing if present
        clean = re.sub(r"^```[a-z]*\n?", "", raw_text.strip(), flags=re.MULTILINE)
        clean = re.sub(r"```$", "", clean.strip())
        parsed = json.loads(clean)
        corrected = parsed.get("corrected_transcript", raw_transcript)
        # Strip the "[0.0-999.0] speaker: " prefix if the model included it
        corrected = re.sub(r"^\[\d+\.\d+-\d+\.\d+\]\s+\w+:\s*", "", corrected).strip()
    except Exception:
        corrected = raw_transcript  # fallback — no change

    return corrected, latency


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _checkpoint_path(args: argparse.Namespace) -> Path:
    """
    Deterministic filename based on run parameters — same args always
    map to the same file, so resume is automatic (no flag needed).
    """
    ctx  = args.context or "all"
    samp = str(args.max_samples) if args.max_samples else "full"
    return RESULTS_DIR / f"eval_phase{args.phase}_{ctx}_{samp}.json"


def _load_checkpoint(path: Path) -> tuple[list[SampleResult], set[str]]:
    """
    Load a partial results file written by a previous (interrupted) run.
    Returns (results_list, set_of_successfully_completed_sample_ids).
    Only successful (error=None) samples are skipped on resume — errored
    samples (e.g. 429s) are retried.
    """
    if not path.exists():
        return [], set()
    try:
        data = json.loads(path.read_text())
        samples = data.get("samples", [])
        results = []
        for s in samples:
            try:
                results.append(SampleResult(**s))
            except Exception:
                pass  # skip malformed entries
        # Only skip samples that actually succeeded — retry errored ones
        completed = {r.sample_id for r in results if r.error is None}
        return results, completed
    except Exception:
        return [], set()


def _flush_checkpoint(
    path: Path,
    results: list[SampleResult],
    args: argparse.Namespace,
    complete: bool = False,
) -> None:
    """Write current results + aggregate to the checkpoint file (atomic via tmp)."""
    valid = [r for r in results if r.error is None]
    n = max(len(valid), 1)

    aggregate: dict[str, Any] = {
        "status":          "complete" if complete else "in_progress",
        "total_samples":   len(results),
        "valid_samples":   len(valid),
        "error_count":     sum(1 for r in results if r.error),
        "phase":           args.phase,
        "sarvam_model":    SARVAM_MODEL,
        "sarvam_mode":     SARVAM_MODE,
        "azure_model":     AZURE_DEPLOYMENT if args.phase == 2 else None,
        "context_filter":  args.context,
        "wer_sarvam":      round(sum(r.wer_sarvam for r in valid) / n, 4),
        "entity_recall_sarvam": round(sum(r.entity_recall_sarvam for r in valid) / n, 4),
    }

    if args.phase == 2:
        corrected_valid = [r for r in valid if r.wer_corrected is not None]
        nc = max(len(corrected_valid), 1)
        aggregate["wer_corrected"] = round(
            sum(r.wer_corrected for r in corrected_valid) / nc, 4
        )
        aggregate["entity_recall_corrected"] = round(
            sum(r.entity_recall_corrected for r in corrected_valid
                if r.entity_recall_corrected is not None) / nc, 4
        )
        aggregate["wer_delta"] = round(
            aggregate["wer_sarvam"] - aggregate["wer_corrected"], 4
        )
        aggregate["entity_recall_delta"] = round(
            aggregate["entity_recall_corrected"] - aggregate["entity_recall_sarvam"], 4
        )

    for ctx_val in ("conversation", "narrated", "demonstration"):
        ctx_samples = [r for r in valid if r.recording_context == ctx_val]
        if ctx_samples:
            aggregate[f"wer_sarvam_{ctx_val}"] = round(
                sum(r.wer_sarvam for r in ctx_samples) / len(ctx_samples), 4
            )

    # Atomic write via temp file in same dir (avoids partial reads on crash)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"aggregate": aggregate, "samples": [asdict(r) for r in results]}, indent=2)
    )
    tmp.replace(path)


def _print_progress(
    i: int,
    total: int,
    results: list[SampleResult],
    errors: int,
    phase: int,
) -> None:
    valid = [r for r in results if r.error is None]
    avg_wer = sum(r.wer_sarvam for r in valid) / max(len(valid), 1)
    avg_er  = sum(r.entity_recall_sarvam for r in valid) / max(len(valid), 1)
    if phase == 2:
        c_valid = [r for r in valid if r.wer_corrected is not None]
        avg_wer_c = sum(r.wer_corrected for r in c_valid) / max(len(c_valid), 1)
        print(
            f"  [{i+1}/{total}] WER: {avg_wer:.3f}→{avg_wer_c:.3f} "
            f"| entity_recall: {avg_er:.3f} | errors: {errors}"
        )
    else:
        print(
            f"  [{i+1}/{total}] WER: {avg_wer:.3f} "
            f"| entity_recall: {avg_er:.3f} | errors: {errors}"
        )


def _print_summary(out_path: Path, results: list[SampleResult], args: argparse.Namespace) -> None:
    valid = [r for r in results if r.error is None]
    data  = json.loads(out_path.read_text())
    agg   = data["aggregate"]

    print(f"\n{'='*60}")
    print(f"  RESULTS — Phase {args.phase}")
    print(f"{'='*60}")
    print(f"  Samples evaluated : {len(valid)}/{len(results)}")
    print(f"  WER (Sarvam)      : {agg['wer_sarvam']:.3f}  ({agg['wer_sarvam']*100:.1f}%)")
    print(f"  Entity recall     : {agg['entity_recall_sarvam']:.3f}  "
          f"({agg['entity_recall_sarvam']*100:.1f}% of drug/entity names correct)")
    if args.phase == 2 and "wer_corrected" in agg:
        print(f"  WER (corrected)   : {agg['wer_corrected']:.3f}  ({agg['wer_corrected']*100:.1f}%)")
        delta = agg["wer_delta"]
        sign  = "↓" if delta > 0 else "↑" if delta < 0 else "="
        print(f"  WER delta         : {sign} {abs(delta):.3f}  "
              f"({'improvement' if delta > 0 else 'regression' if delta < 0 else 'no change'})")
        print(f"  Entity recall Δ   : {agg.get('entity_recall_delta', 0):+.3f}")
    print(f"\n  Results saved to  : {out_path}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def evaluate(args: argparse.Namespace) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = _checkpoint_path(args)

    # --- Resume detection ---
    results, completed_ids = _load_checkpoint(out_path)
    resuming = bool(completed_ids)

    print(f"\n{'='*60}")
    print(f"  Voice Pipeline Evaluation")
    print(f"  Phase: {args.phase}  |  Max samples: {args.max_samples or 'all'}")
    print(f"  Context filter: {args.context or 'all'}")
    print(f"  Sarvam model:   {SARVAM_MODEL} ({SARVAM_MODE}, {SARVAM_LANG_CODE})")
    if args.phase == 2:
        print(f"  Azure model:    {AZURE_DEPLOYMENT}")
    if resuming:
        print(f"  RESUMING from checkpoint: {len(completed_ids)} samples already done")
    print(f"  Checkpoint file : {out_path}")
    print(f"{'='*60}\n")

    # Load dataset — disable audio decoding (avoids torchcodec dependency);
    # we send raw bytes directly to Sarvam which accepts m4a/mp3/wav.
    print("Loading ekacare/eka-medical-asr-evaluation-dataset (English)...")
    dataset = load_dataset(
        "ekacare/eka-medical-asr-evaluation-dataset",
        "en",
        split="test",
    ).cast_column("audio", Audio(decode=False))
    print(f"  Loaded {len(dataset)} samples\n")

    if args.context:
        # Filter only on metadata column to avoid triggering audio decoding
        meta = dataset.select_columns(["recording_context"])
        indices = [
            i for i, x in enumerate(meta)
            if x["recording_context"] == args.context
        ]
        dataset = dataset.select(indices)
        print(f"  After context filter ({args.context}): {len(dataset)} samples\n")

    if args.max_samples:
        dataset = dataset.select(range(min(args.max_samples, len(dataset))))
        print(f"  Using first {len(dataset)} samples\n")

    errors = sum(1 for r in results if r.error)
    total  = len(dataset)

    for i, sample in enumerate(dataset):
        sample_id = sample.get("file_name", f"sample_{i}")
        reference = sample.get("text", "").strip()
        entities  = _parse_medical_entities(sample.get("medical_entities", []))
        ctx       = sample.get("recording_context", "unknown")
        typ       = sample.get("type_concept", "unknown")

        if not reference:
            continue

        # Skip already-completed samples (resume path)
        if sample_id in completed_ids:
            continue

        # Convert audio to WAV bytes
        try:
            audio_bytes = _audio_bytes_to_wav(sample["audio"])
        except Exception as exc:
            print(f"  [{i+1}] AUDIO ERROR {sample_id}: {exc}")
            errors += 1
            continue

        # --- Phase 1: Sarvam STT ---
        sarvam_transcript = ""
        sarvam_latency    = 0.0
        sample_error      = None
        # Derive filename/extension from original path (m4a, mp3, wav, etc.)
        orig_path = sample.get("audio", {}).get("path") or ""
        ext = Path(orig_path).suffix or ".m4a"
        try:
            sarvam_transcript, sarvam_latency = call_sarvam(audio_bytes, f"sample_{i}{ext}")
        except Exception as exc:
            sample_error = str(exc)
            errors += 1
            print(f"  [{i+1}] SARVAM ERROR: {exc}")

        time.sleep(SARVAM_SLEEP_S)

        # --- Phase 2: TranscriptCorrector ---
        corrected_transcript    = None
        llm_latency             = None
        entity_recall_corrected = None
        wer_corrected           = None

        if args.phase == 2 and sarvam_transcript and not sample_error:
            try:
                corrected_transcript, llm_latency = call_corrector(sarvam_transcript)
                wer_corrected = compute_wer(
                    _normalise(reference), _normalise(corrected_transcript)
                )
                entity_recall_corrected = _entity_recall(entities, corrected_transcript)
            except Exception as exc:
                corrected_transcript = sarvam_transcript
                sample_error = (sample_error or "") + f" | LLM: {exc}"
                print(f"  [{i+1}] LLM ERROR: {exc}")

            time.sleep(LLM_SLEEP_S)

        # --- Metrics ---
        wer_sarvam           = compute_wer(
            _normalise(reference), _normalise(sarvam_transcript)
        ) if sarvam_transcript else 1.0
        entity_recall_sarvam = _entity_recall(entities, sarvam_transcript)

        result = SampleResult(
            sample_id=sample_id,
            reference=reference,
            sarvam_transcript=sarvam_transcript,
            corrected_transcript=corrected_transcript,
            medical_entities=entities,
            wer_sarvam=round(wer_sarvam, 4),
            wer_corrected=round(wer_corrected, 4) if wer_corrected is not None else None,
            entity_recall_sarvam=round(entity_recall_sarvam, 4),
            entity_recall_corrected=(
                round(entity_recall_corrected, 4) if entity_recall_corrected is not None else None
            ),
            recording_context=ctx,
            type_concept=typ,
            sarvam_latency_s=round(sarvam_latency, 3),
            llm_latency_s=round(llm_latency, 3) if llm_latency else None,
            error=sample_error,
        )
        results.append(result)
        completed_ids.add(sample_id)

        # Progress + checkpoint every N samples
        if (len(results) % CHECKPOINT_EVERY == 0) or (i + 1 == total):
            _print_progress(i, total, results, errors, args.phase)
            _flush_checkpoint(out_path, results, args, complete=(i + 1 == total))

    # Final flush (marks complete)
    _flush_checkpoint(out_path, results, args, complete=True)
    _print_summary(out_path, results, args)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate voice pipeline against EkaCare ASR dataset")
    parser.add_argument(
        "--phase", type=int, choices=[1, 2], default=1,
        help="1 = Sarvam STT only; 2 = STT + LLM correction delta",
    )
    parser.add_argument(
        "--max-samples", type=int, default=None,
        help="Limit to N samples (default: full dataset of 3,620)",
    )
    parser.add_argument(
        "--context", choices=["conversation", "narrated", "demonstration"], default=None,
        help="Filter by recording context (default: all types)",
    )
    args = parser.parse_args()
    evaluate(args)
