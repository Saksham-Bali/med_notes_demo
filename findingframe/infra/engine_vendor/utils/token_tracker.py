"""
Token usage tracker for LLM calls across the pipeline.

Provides per-call, per-component, and per-run token accounting
with JSON export for cost analysis and reproducibility.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class TokenCall:
    """Record of a single LLM call."""
    timestamp: str
    component: str  # e.g., "extraction", "grounding", "normalizer", "judge"
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_seconds: float
    call_type: str  # e.g., "single_report", "paired_report", "llm_grounding", "dedup"
    patient_id: Optional[str] = None
    report_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class ComponentSummary:
    """Aggregated token usage for a component."""
    component: str
    call_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    failed_calls: int = 0


class TokenTracker:
    """
    Thread-safe token usage tracker for the TMC pipeline.

    Usage:
        tracker = TokenTracker()
        tracker.start_run("eval_v14", patient_id="10000935")
        # ... after each LLM call:
        tracker.record_call(component="extraction", prompt_tokens=3200, completion_tokens=1500, ...)
        # ... at end:
        tracker.end_run()
        tracker.save("./outputs/token_usage.json")
    """

    _instance: Optional["TokenTracker"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._calls: list[TokenCall] = []
        self._current_run_id: Optional[str] = None
        self._current_patient_id: Optional[str] = None
        self._run_start_time: Optional[float] = None
        self._lock = threading.Lock()

    def start_run(self, run_id: str, patient_id: Optional[str] = None):
        """Start a tracked evaluation run."""
        with self._lock:
            self._current_run_id = run_id
            self._current_patient_id = patient_id
            self._run_start_time = time.time()
            self._calls = []

    def end_run(self) -> dict[str, Any]:
        """End current run and return summary."""
        with self._lock:
            duration = (
                time.time() - self._run_start_time
                if self._run_start_time
                else 0.0
            )
            summary = self._build_summary()
            summary["run_id"] = self._current_run_id
            summary["patient_id"] = self._current_patient_id
            summary["run_duration_seconds"] = round(duration, 2)
            summary["run_end_time"] = datetime.now().isoformat()
            return summary

    def record_call(
        self,
        component: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_seconds: float,
        call_type: str = "unknown",
        patient_id: Optional[str] = None,
        report_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        """Record a single LLM call."""
        call = TokenCall(
            timestamp=datetime.now().isoformat(),
            component=component,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_seconds=duration_seconds,
            call_type=call_type,
            patient_id=patient_id or self._current_patient_id,
            report_id=report_id,
            success=success,
            error_message=error_message,
        )
        with self._lock:
            self._calls.append(call)

    def record_from_response(
        self,
        component: str,
        model: str,
        response: Any,
        duration_seconds: float,
        call_type: str = "unknown",
        patient_id: Optional[str] = None,
        report_id: Optional[str] = None,
    ):
        """
        Record call from an OpenAI/Azure response object.
        Extracts usage metadata automatically.
        """
        prompt_tokens = 0
        completion_tokens = 0
        try:
            if hasattr(response, "usage") and response.usage:
                usage = response.usage
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            elif isinstance(response, dict):
                usage = response.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
        except Exception:
            pass

        self.record_call(
            component=component,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_seconds=duration_seconds,
            call_type=call_type,
            patient_id=patient_id,
            report_id=report_id,
            success=True,
        )

    def get_summary(self) -> dict[str, Any]:
        """Get current summary without ending run."""
        with self._lock:
            return self._build_summary()

    def _build_summary(self) -> dict[str, Any]:
        """Build summary from recorded calls."""
        component_summaries: dict[str, ComponentSummary] = {}
        call_types: dict[str, int] = defaultdict(int)

        for call in self._calls:
            comp = call.component
            if comp not in component_summaries:
                component_summaries[comp] = ComponentSummary(component=comp)
            cs = component_summaries[comp]
            cs.call_count += 1
            cs.total_prompt_tokens += call.prompt_tokens
            cs.total_completion_tokens += call.completion_tokens
            cs.total_tokens += call.total_tokens
            cs.total_duration_seconds += call.duration_seconds
            if not call.success:
                cs.failed_calls += 1

            call_types[call.call_type] += 1

        total_prompt = sum(c.total_prompt_tokens for c in component_summaries.values())
        total_completion = sum(c.total_completion_tokens for c in component_summaries.values())
        total_tokens = sum(c.total_tokens for c in component_summaries.values())
        total_duration = sum(c.total_duration_seconds for c in component_summaries.values())
        total_calls = sum(c.call_count for c in component_summaries.values())

        # OpenRouter pricing baseline (per 1M tokens) for project budgeting
        INPUT_PRICE_PER_1M = 0.75
        OUTPUT_PRICE_PER_1M = 4.50

        estimated_cost = (
            (total_prompt / 1_000_000) * INPUT_PRICE_PER_1M +
            (total_completion / 1_000_000) * OUTPUT_PRICE_PER_1M
        )

        return {
            "run_id": self._current_run_id,
            "patient_id": self._current_patient_id,
            "run_start_time": (
                datetime.fromtimestamp(self._run_start_time).isoformat()
                if self._run_start_time
                else None
            ),
            "total_calls": total_calls,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(estimated_cost, 4),
            "total_duration_seconds": round(total_duration, 2),
            "components": {
                name: asdict(summary)
                for name, summary in component_summaries.items()
            },
            "call_types": dict(call_types),
        }

    def save(self, path: Optional[str] = None) -> str:
        """Save full token usage log to JSON."""
        if path is None:
            path = f"./outputs/token_usage_{self._current_run_id or 'unknown'}.json"

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            data = {
                "summary": self._build_summary(),
                "calls": [asdict(c) for c in self._calls],
            }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return path

    def print_summary(self):
        """Print human-readable summary to console."""
        summary = self.get_summary()
        print("\n" + "=" * 60)
        print("TOKEN USAGE SUMMARY")
        print("=" * 60)
        print(f"Run ID:       {summary.get('run_id', 'N/A')}")
        print(f"Patient:      {summary.get('patient_id', 'N/A')}")
        print(f"Total Calls:  {summary['total_calls']}")
        print(f"Prompt:       {summary['total_prompt_tokens']:,} tokens")
        print(f"Completion:   {summary['total_completion_tokens']:,} tokens")
        print(f"Total:        {summary['total_tokens']:,} tokens")
        print(f"Est. Cost:    ${summary['estimated_cost_usd']:.4f} USD")
        print(f"Duration:     {summary['total_duration_seconds']:.1f}s")
        print("-" * 60)
        print("By Component:")
        for name, comp in summary.get("components", {}).items():
            print(
                f"  {name:20s} {comp['call_count']:>3} calls  "
                f"{comp['total_tokens']:>7,} tokens  "
                f"${(comp['total_prompt_tokens']/1e6*0.75 + comp['total_completion_tokens']/1e6*4.50):.4f}"
            )
        print("=" * 60 + "\n")

    def reset(self):
        """Clear all recorded calls."""
        with self._lock:
            self._calls = []
            self._current_run_id = None
            self._current_patient_id = None
            self._run_start_time = None


# Global singleton instance
token_tracker = TokenTracker()


def get_tracker() -> TokenTracker:
    """Get the global token tracker instance."""
    return token_tracker
