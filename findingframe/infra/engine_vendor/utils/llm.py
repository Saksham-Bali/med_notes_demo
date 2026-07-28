"""
Shared LLM utilities for project-wide LLM usage.
Provides retries, consistent settings, and robust JSON extraction.
"""

import json
import os
import threading
import time
from collections import deque
from typing import Any, Optional

import requests
import yaml
from dotenv import load_dotenv

# Token usage tracking (singleton)
from .token_tracker import get_tracker


# ---------------------------------------------------------------------------
# Rate limiter for OpenAI direct API (5 calls/min)
# ---------------------------------------------------------------------------
class _RateLimiter:
    """Thread-safe rolling-window limiter for request start times.

    The OpenAI quota limits starts per minute, not concurrent in-flight calls.
    A burst of ``calls_per_minute`` threads may therefore start immediately;
    later callers wait until a slot leaves the rolling window.
    """

    def __init__(
        self,
        calls_per_minute: int = 5,
        *,
        window_seconds: float = 60.0,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        if calls_per_minute < 1:
            raise ValueError("calls_per_minute must be at least 1")
        self._calls_per_window = calls_per_minute
        self._window_seconds = window_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._starts: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self):
        while True:
            with self._lock:
                now = self._clock()
                cutoff = now - self._window_seconds
                while self._starts and self._starts[0] <= cutoff:
                    self._starts.popleft()
                if len(self._starts) < self._calls_per_window:
                    self._starts.append(now)
                    return
                wait_for = max(
                    0.0,
                    self._starts[0] + self._window_seconds - now,
                )
            self._sleeper(wait_for)

_openai_rate_limiter = _RateLimiter(calls_per_minute=5)


# ---------------------------------------------------------------------------
# Model name mapping: OpenRouter prefix -> direct OpenAI name
# ---------------------------------------------------------------------------
_OPENROUTER_TO_OPENAI = {
    "openai/gpt-5": "gpt-5",
    "openai/gpt-5.1": "gpt-5.1",
    "openai/gpt-5.2": "gpt-5.2",
    "openai/gpt-5.4": "gpt-5.4-2026-03-05",
    "openai/gpt-5.5": "gpt-5.2",   # gpt-5.5 not available direct; fall back to gpt-5.2
    "openai/gpt-4o": "gpt-4o",
    "openai/gpt-4.1": "gpt-4.1",
    "openai/o1": "o1",
    "openai/o3": "o3",
}


def _to_openai_model(model: str) -> str:
    """Map an OpenRouter-prefixed model name to a direct OpenAI model name."""
    if model in _OPENROUTER_TO_OPENAI:
        return _OPENROUTER_TO_OPENAI[model]
    # Strip common prefixes
    for prefix in ("openai/", "openai."):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def _supports_reasoning(model: str) -> bool:
    """Return True if the model supports a reasoning.effort parameter (OpenRouter only)."""
    return False  # OpenAI direct API does not use reasoning.effort; reasoning is automatic


def _is_reasoning_model(model: str) -> bool:
    """Return True if the model is a reasoning model that auto-consumes tokens for reasoning."""
    model_lower = model.lower()
    return any(m in model_lower for m in ("gpt-5", "o1", "o3"))


def _supports_temperature_zero(model: str) -> bool:
    """Return True if the model supports temperature=0."""
    model_lower = model.lower()
    # GPT-5-family on direct OpenAI API does NOT support temperature=0
    if any(m in model_lower for m in ("gpt-5", "o1", "o3")):
        return False
    return True


# ---------------------------------------------------------------------------
# OpenAI direct client
# ---------------------------------------------------------------------------
class OpenAILLMClient:
    """
    Thin client for the OpenAI direct API.
    Same interface as OpenRouterLLMClient for drop-in compatibility.
    Rate-limited to 5 calls/minute across all instances.
    """

    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5",
        timeout: int = 300,
        retries: int = 2,
    ):
        self.api_key = api_key
        # Normalise model name: strip openai/ prefix if present
        self.model = _to_openai_model(model)
        self.timeout = timeout
        self.retries = retries
        self._tracker_component = "openai"
        self._tracker_call_type = "completion"

    def set_tracker_context(self, component: str, call_type: str = "unknown"):
        self._tracker_component = component
        self._tracker_call_type = call_type

    def complete(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float | None = 0.0,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        attempt = 0
        last_error: Exception | None = None
        # Reasoning models need a larger budget; reasoning tokens are
        # counted against max_completion_tokens.
        base_budget = max(int(max_tokens), 128)
        if _is_reasoning_model(self.model) and base_budget < 8000:
            base_budget = 8000
        token_budget = base_budget
        start_time = time.time()
        tracker = get_tracker()

        while attempt <= self.retries:
            _openai_rate_limiter.wait()

            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                # OpenAI direct API uses max_completion_tokens for reasoning models
                "max_completion_tokens": token_budget,
            }
            # GPT-5-family on direct API does NOT support temperature=0
            if temperature is not None and _supports_temperature_zero(self.model):
                payload["temperature"] = temperature

            try:
                response = requests.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                duration = time.time() - start_time

                tracker.record_from_response(
                    component=getattr(self, "_tracker_component", "openai"),
                    model=self.model,
                    response=data,
                    duration_seconds=duration,
                    call_type=getattr(self, "_tracker_call_type", "openai_completion"),
                )

                content = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                if not content or not str(content).strip():
                    raise ValueError("OpenAI returned empty content")
                return str(content)
            except Exception as e:
                last_error = e
                if "empty content" in str(e).lower():
                    token_budget = min(max(token_budget * 2, base_budget), 16000)
                attempt += 1
                if attempt > self.retries:
                    break
                time.sleep(min(2 ** attempt, 10))
        raise last_error

    def chat(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        return self.complete(
            prompt=prompt,
            max_tokens=int(max_tokens or 2000),
            temperature=temperature,
        )


class OpenRouterLLMClient:
    """
    Thin client for OpenRouter API.
    Can be used for extraction, judging, normalization, and other project tasks.
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-5.4",
        timeout: int = 60,
        retries: int = 2,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self._tracker_component = "openrouter"
        self._tracker_call_type = "completion"

    def set_tracker_context(self, component: str, call_type: str = "unknown"):
        """Set token tracker context for subsequent calls."""
        self._tracker_component = component
        self._tracker_call_type = call_type

    def complete(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float | None = 0.0,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tmc-pipeline",  # required by OpenRouter
            "X-Title": "tmc-pipeline",
        }
        attempt = 0
        last_error: Exception | None = None
        token_budget = max(int(max_tokens), 128)
        start_time = time.time()
        tracker = get_tracker()

        while attempt <= self.retries:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": token_budget,
                # GPT-5-family models can otherwise spend the entire budget on reasoning.
                "reasoning": {"effort": os.getenv("OPENROUTER_REASONING_EFFORT", "medium")},
            }
            if temperature is not None:
                payload["temperature"] = temperature
            try:
                response = requests.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                duration = time.time() - start_time

                # Track token usage (OpenRouter returns usage in response)
                tracker.record_from_response(
                    component=getattr(self, "_tracker_component", "openrouter"),
                    model=self.model,
                    response=data,
                    duration_seconds=duration,
                    call_type=getattr(self, "_tracker_call_type", "openrouter_completion"),
                )

                content = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                if not content or not str(content).strip():
                    raise ValueError("OpenRouter returned empty content")
                return str(content)
            except Exception as e:
                last_error = e
                if "empty content" in str(e).lower():
                    token_budget = min(max(token_budget * 2, 256), 8192)
                attempt += 1
                if attempt > self.retries:
                    break
                time.sleep(min(2**attempt, 10))
        raise last_error

    def chat(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        # OpenRouter does not guarantee json_schema Structured Outputs here;
        # ignore the schema hint and use the regular completion path.
        return self.complete(
            prompt=prompt,
            max_tokens=int(max_tokens or 2000),
            temperature=temperature,
        )


def _load_config_defaults() -> dict:
    config_path = os.path.join("config", "config.yaml")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("llm", {}) or {}
    except Exception:
        return {}


def _strip_code_fences(text: str) -> str:
    if "```" not in text:
        return text
    if "```json" in text:
        return text.split("```json")[1].split("```")[0]
    return text.split("```")[1].split("```")[0]


def extract_json_from_text(text: str) -> str:
    """
    Extract the first JSON object or array from a text blob.
    Handles code fences and ignores leading/trailing non-JSON text.
    """
    cleaned = _strip_code_fences(text).strip()
    if not cleaned:
        raise ValueError("Empty response")

    # Find first JSON object/array start
    start_idx = None
    for i, ch in enumerate(cleaned):
        if ch in "{[":
            start_idx = i
            break

    if start_idx is None:
        raise ValueError("No JSON object or array found")

    stack = []
    in_string = False
    escape = False
    for i in range(start_idx, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        else:
            if ch == '"':
                in_string = True
                continue
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if not stack:
                    raise ValueError("Unbalanced JSON brackets")
                open_bracket = stack.pop()
                if (open_bracket == "{" and ch != "}") or (
                    open_bracket == "[" and ch != "]"
                ):
                    raise ValueError("Mismatched JSON brackets")
                if not stack:
                    return cleaned[start_idx : i + 1].strip()

    raise ValueError("No complete JSON object or array found")


def parse_json_from_text(text: str) -> Any:
    json_str = extract_json_from_text(text)
    return json.loads(json_str)


def _resolve_model_name(defaults: dict, env_key: str = "OPENROUTER_MODEL") -> str:
    configured = str(
        os.getenv(env_key) or defaults.get("model") or defaults.get("deployment") or ""
    ).strip()
    if configured:
        return configured if "/" in configured else f"openai/{configured}"
    return "openai/gpt-5.5"

def _extract_message_text(message: Any) -> str:
    """
    Normalize chat-completions message payloads to plain text.
    Handles string and list/dict content block variants.
    """
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict):
                # Common shapes: {"type":"text","text":"..."} or {"text":{"value":"..."}}
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
                elif isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str):
                        chunks.append(value)
                continue
            text_attr = getattr(item, "text", None)
            if isinstance(text_attr, str):
                chunks.append(text_attr)
            elif text_attr is not None:
                value = getattr(text_attr, "value", None)
                if isinstance(value, str):
                    chunks.append(value)
        return "\n".join(part for part in chunks if part).strip()
    return ""


def create_routine_llm_client() -> "OpenRouterLLMClient":
    """
    Create a lightweight routine LLM client for recurring tasks.
    Reads from config.yaml `routine` block and uses OpenRouter.
    """
    load_dotenv(dotenv_path="config/.env")
    config_path = os.path.join("config", "config.yaml")
    routine_cfg: dict = {}
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                routine_cfg = yaml.safe_load(f).get("routine", {}) or {}
        except Exception:
            pass
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required for routine LLM client")
    model = str(
        os.getenv("OPENROUTER_ROUTINE_MODEL")
        or routine_cfg.get("model")
        or routine_cfg.get("deployment")
        or "google/gemini-2.5-pro"
    ).strip()
    timeout = int(routine_cfg.get("timeout", 60))
    retries = int(routine_cfg.get("retries", 2))
    return OpenRouterLLMClient(
        api_key=api_key, model=model, timeout=timeout, retries=retries
    )


def create_default_llm_client(
    deployment: Optional[str] = None,
    provider: Optional[str] = None,
):
    """
    Create the default LLM client for extraction/normalization/rendering/progression.

    Supports ``openrouter`` (default) and ``openai`` providers.
    Set ``LLM_PROVIDER=openai`` in the environment to switch.
    """
    load_dotenv(dotenv_path="config/.env")
    defaults = _load_config_defaults()
    provider_raw = provider or os.getenv("LLM_PROVIDER") or defaults.get("provider") or "openrouter"
    provider_norm = str(provider_raw).strip().lower()
    is_openrouter = provider_norm in {"openrouter", "open_router"}
    is_openai = provider_norm in {"openai", "open_ai"}

    if not is_openrouter and not is_openai:
        raise ValueError(
            f"Unsupported LLM provider {provider_raw!r}; expected 'openrouter' or 'openai'"
        )

    if is_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required when LLM provider is openrouter")
        model = _resolve_model_name(defaults)
        timeout = int(os.getenv("OPENROUTER_TIMEOUT") or defaults.get("timeout", 60))
        retries = int(os.getenv("OPENROUTER_RETRIES") or defaults.get("retries", 2))
        return OpenRouterLLMClient(
            api_key=api_key,
            model=model,
            timeout=timeout,
            retries=retries,
        )

    # OpenAI direct provider
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required when LLM provider is openai")
    model = str(
        os.getenv("OPENAI_MODEL") or deployment or defaults.get("model") or "gpt-5"
    ).strip()
    timeout = int(os.getenv("OPENAI_TIMEOUT") or defaults.get("timeout", 300))
    retries = int(os.getenv("OPENAI_RETRIES") or defaults.get("retries", 2))
    return OpenAILLMClient(
        api_key=api_key,
        model=model,
        timeout=timeout,
        retries=retries,
    )
