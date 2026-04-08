from errors import FallbackUnavailableError


class GoogleTranslateClient:
    async def translate_text(
        self,
        *,
        text: str,
        source_language_code: str,
        target_language_code: str = "en",
    ) -> str:
        try:
            from google.cloud import translate_v2 as translate
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise FallbackUnavailableError("Google Translate fallback requires google-cloud-translate.") from exc

        client = translate.Client()
        response = client.translate(
            text,
            source_language=source_language_code.split("-", 1)[0],
            target_language=target_language_code.split("-", 1)[0],
        )
        return str(response["translatedText"]).strip()
