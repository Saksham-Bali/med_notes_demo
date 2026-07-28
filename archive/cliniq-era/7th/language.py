from __future__ import annotations

TRANSLATION_LANGUAGES: dict[str, str] = {
    "as-IN": "Assamese",
    "bn-IN": "Bengali",
    "brx-IN": "Bodo",
    "doi-IN": "Dogri",
    "en-IN": "English",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ks-IN": "Kashmiri",
    "kok-IN": "Konkani",
    "mai-IN": "Maithili",
    "ml-IN": "Malayalam",
    "mni-IN": "Manipuri",
    "mr-IN": "Marathi",
    "ne-IN": "Nepali",
    "od-IN": "Odia",
    "pa-IN": "Punjabi",
    "sa-IN": "Sanskrit",
    "sat-IN": "Santali",
    "sd-IN": "Sindhi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "ur-IN": "Urdu",
}

TTS_LANGUAGES: dict[str, str] = {
    "bn-IN": "Bengali",
    "en-IN": "English",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "od-IN": "Odia",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
}

LANGUAGE_ALIASES: dict[str, str] = {
    "as": "as-IN",
    "as-in": "as-IN",
    "bn": "bn-IN",
    "bn-in": "bn-IN",
    "bodo": "brx-IN",
    "brx": "brx-IN",
    "brx-in": "brx-IN",
    "doi": "doi-IN",
    "doi-in": "doi-IN",
    "dogri": "doi-IN",
    "en": "en-IN",
    "en-in": "en-IN",
    "english": "en-IN",
    "gu": "gu-IN",
    "gu-in": "gu-IN",
    "gujarati": "gu-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "hindi": "hi-IN",
    "kn": "kn-IN",
    "kn-in": "kn-IN",
    "kannada": "kn-IN",
    "kok": "kok-IN",
    "kok-in": "kok-IN",
    "ks": "ks-IN",
    "ks-in": "ks-IN",
    "mai": "mai-IN",
    "mai-in": "mai-IN",
    "ml": "ml-IN",
    "ml-in": "ml-IN",
    "malayalam": "ml-IN",
    "mni": "mni-IN",
    "mni-in": "mni-IN",
    "mr": "mr-IN",
    "mr-in": "mr-IN",
    "marathi": "mr-IN",
    "ne": "ne-IN",
    "ne-in": "ne-IN",
    "od": "od-IN",
    "od-in": "od-IN",
    "or": "od-IN",
    "or-in": "od-IN",
    "odia": "od-IN",
    "pa": "pa-IN",
    "pa-in": "pa-IN",
    "punjabi": "pa-IN",
    "sa": "sa-IN",
    "sa-in": "sa-IN",
    "sat": "sat-IN",
    "sat-in": "sat-IN",
    "sd": "sd-IN",
    "sd-in": "sd-IN",
    "ta": "ta-IN",
    "ta-in": "ta-IN",
    "tamil": "ta-IN",
    "te": "te-IN",
    "te-in": "te-IN",
    "telugu": "te-IN",
    "ur": "ur-IN",
    "ur-in": "ur-IN",
    "urdu": "ur-IN",
}


def normalize_language_code(language_code: str) -> str:
    raw = language_code.strip()
    if raw in TRANSLATION_LANGUAGES:
        return raw

    lowered = raw.lower().replace("_", "-")
    if lowered in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[lowered]

    if lowered.endswith("-in"):
        prefix = lowered[:-3]
        if prefix in LANGUAGE_ALIASES:
            return LANGUAGE_ALIASES[prefix]

    raise ValueError(f"Unsupported language code: {language_code}")


def normalize_translation_language(language_code: str) -> str:
    normalized = normalize_language_code(language_code)
    if normalized not in TRANSLATION_LANGUAGES:
        raise ValueError(f"Translation is not supported for language: {language_code}")
    return normalized


def normalize_tts_language(language_code: str) -> str:
    normalized = normalize_language_code(language_code)
    if normalized not in TTS_LANGUAGES:
        raise ValueError(f"Audio generation is not supported for language: {language_code}")
    return normalized


def is_tts_supported(language_code: str) -> bool:
    try:
        normalized = normalize_language_code(language_code)
    except ValueError:
        return False
    return normalized in TTS_LANGUAGES


def language_name(language_code: str) -> str:
    normalized = normalize_language_code(language_code)
    return TRANSLATION_LANGUAGES[normalized]


def language_file_suffix(language_code: str) -> str:
    normalized = normalize_language_code(language_code)
    return normalized.split("-", maxsplit=1)[0].lower()

