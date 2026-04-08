from agents.language_detector import choose_original_mode, is_code_mixed_text, normalize_language_hint


def test_choose_original_mode_prefers_codemix_for_unknown_language() -> None:
    assert choose_original_mode(None) == "codemix"
    assert choose_original_mode("hi-IN") == "codemix"
    assert choose_original_mode("en-IN") == "transcribe"


def test_language_hint_short_codes_are_normalized() -> None:
    assert normalize_language_hint("hi") == "hi-IN"
    assert normalize_language_hint("en") == "en-IN"


def test_code_mix_detection_detects_mixed_scripts() -> None:
    assert is_code_mixed_text("मेरा phone number hai") is True
    assert is_code_mixed_text("This is only English") is False
