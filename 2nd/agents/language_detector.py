import re

from errors import AudioValidationError

LANGUAGE_ALIASES = {
    "as": "as-IN",
    "bn": "bn-IN",
    "brx": "brx-IN",
    "doi": "doi-IN",
    "en": "en-IN",
    "gu": "gu-IN",
    "hi": "hi-IN",
    "kn": "kn-IN",
    "kok": "kok-IN",
    "ks": "ks-IN",
    "mai": "mai-IN",
    "ml": "ml-IN",
    "mni": "mni-IN",
    "mr": "mr-IN",
    "ne": "ne-IN",
    "od": "od-IN",
    "or": "od-IN",
    "pa": "pa-IN",
    "sa": "sa-IN",
    "sat": "sat-IN",
    "sd": "sd-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "unknown": "unknown",
    "ur": "ur-IN",
}


def normalize_language_hint(language_hint: str | None) -> str | None:
    if not language_hint:
        return None

    normalized = language_hint.strip()
    if not normalized:
        return None
    if normalized in LANGUAGE_ALIASES.values():
        return normalized

    lowered = normalized.lower()
    if lowered in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[lowered]

    raise AudioValidationError(f"Unsupported language_hint '{language_hint}'. Use BCP-47 like hi-IN or a short code like hi.")


def primary_language_code(language_code: str | None) -> str | None:
    if not language_code:
        return None
    return language_code.split("-", 1)[0].lower()


def choose_original_mode(language_code: str | None, default_non_english_mode: str = "codemix") -> str:
    if language_code is None or language_code == "unknown":
        return default_non_english_mode
    if primary_language_code(language_code) == "en":
        return "transcribe"
    return default_non_english_mode


def is_code_mixed_text(text: str) -> bool:
    has_ascii_words = bool(re.search(r"[A-Za-z]{2,}", text))
    has_non_ascii = any(ord(char) > 127 for char in text)
    return has_ascii_words and has_non_ascii
