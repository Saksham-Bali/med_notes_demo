"""
Shared LLM utilities for Azure OpenAI usage.
Provides retries, consistent settings, and robust JSON extraction.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Azure configuration defaults (override via environment variables)
# ---------------------------------------------------------------------------
AZURE_ENDPOINT = os.environ.get(
    "AZURE_ENDPOINT",
    "https://sherpartap1101-5077-resource.cognitiveservices.azure.com/",
)
AZURE_DEPLOYMENT = os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini")
AZURE_API_VERSION = os.environ.get("AZURE_API_VERSION", "2025-01-01-preview")
AZURE_API_KEY = os.environ.get("AZURE_API_KEY", "")


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


@dataclass
class LLMSettings:
    deployment: str
    max_tokens: int
    temperature: Optional[float]
    retries: int
    timeout: int


def _is_temperature_unsupported_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "temperature" in text and (
        "unsupported value" in text
        or "does not support" in text
        or "only the default" in text
    )


def _is_token_parameter_unsupported_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "max_completion_tokens" in text and (
        "unrecognized" in text
        or "unexpected keyword" in text
        or "extra_forbidden" in text
        or "unknown parameter" in text
    )


def _is_max_tokens_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return ("max" in text and "token" in text) and (
        "too large" in text
        or "maximum context length" in text
        or "must be less than" in text
        or "out of range" in text
    )


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


class AzureLLMClient:
    """
    Thin wrapper around Azure OpenAI client with retries and defaults.
    Uses environment variables for configuration.
    """

    def __init__(self, deployment: Optional[str] = None):
        self.settings = LLMSettings(
            deployment=deployment or AZURE_DEPLOYMENT,
            max_tokens=int(os.environ.get("AZURE_MAX_TOKENS", "4000")),
            temperature=None,
            retries=int(os.environ.get("AZURE_RETRIES", "2")),
            timeout=int(os.environ.get("AZURE_TIMEOUT", "60")),
        )

        from openai import AzureOpenAI

        self.client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=AZURE_API_VERSION,
        )

    def chat(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        """Send a chat completion request."""
        attempt = 0
        last_error: Optional[Exception] = None
        requested_temperature = (
            temperature if temperature is not None else self.settings.temperature
        )
        disable_temperature = False
        use_max_completion_tokens = True
        token_budget = int(max_tokens or self.settings.max_tokens)
        token_budget = max(token_budget, 256)

        while attempt <= self.settings.retries:
            try:
                request_kwargs: dict[str, Any] = {
                    "model": self.settings.deployment,
                    "messages": [{"role": "user", "content": prompt}],
                    "timeout": self.settings.timeout,
                }
                if use_max_completion_tokens:
                    request_kwargs["max_completion_tokens"] = token_budget
                else:
                    request_kwargs["max_tokens"] = token_budget
                if requested_temperature is not None and not disable_temperature:
                    request_kwargs["temperature"] = requested_temperature

                if json_schema is not None:
                    request_kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": json_schema,
                    }

                response = self.client.chat.completions.create(**request_kwargs)
                content = _extract_message_text(response.choices[0].message)
                if not content or not content.strip():
                    raise ValueError("LLM returned empty content")
                return content
            except Exception as e:
                if json_schema is not None and (
                    "response_format" in str(e).lower()
                    or "json_schema" in str(e).lower()
                    or "unsupported" in str(e).lower()
                ):
                    import warnings
                    warnings.warn(
                        f"[LLM] Structured Outputs not supported; falling back. Error: {e}",
                        stacklevel=2,
                    )
                    json_schema = None
                    continue
                if (
                    not disable_temperature
                    and requested_temperature is not None
                    and _is_temperature_unsupported_error(e)
                ):
                    import warnings
                    warnings.warn(
                        f"[LLM] Deployment does not support temperature; retrying without. Error: {e}",
                        stacklevel=2,
                    )
                    disable_temperature = True
                    continue
                if use_max_completion_tokens and _is_token_parameter_unsupported_error(e):
                    use_max_completion_tokens = False
                    continue
                if _is_max_tokens_limit_error(e):
                    token_budget = max(256, int(token_budget * 0.7))
                elif "empty content" in str(e).lower():
                    token_budget = max(256, int(token_budget * 0.7))
                last_error = e
                attempt += 1
                if attempt > self.settings.retries:
                    break
                time.sleep(min(2**attempt, 10))

        if last_error and "empty content" in str(last_error).lower():
            try:
                recovery_kwargs: dict[str, Any] = {
                    "model": self.settings.deployment,
                    "messages": [{"role": "user", "content": prompt}],
                    "timeout": self.settings.timeout,
                    "max_completion_tokens": min(token_budget, 1024),
                }
                response = self.client.chat.completions.create(**recovery_kwargs)
                content = _extract_message_text(response.choices[0].message)
                if content and content.strip():
                    return content
            except Exception:
                pass
        raise last_error  # type: ignore[misc]


def create_default_llm_client(
    deployment: Optional[str] = None,
    provider: Optional[str] = None,
) -> AzureLLMClient:
    """Create the default LLM client (Azure OpenAI)."""
    return AzureLLMClient(deployment=deployment or AZURE_DEPLOYMENT)
