from sarvamai import AsyncSarvamAI

from config import Settings
from errors import ProviderError


class SarvamTextTranslationClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = AsyncSarvamAI(api_subscription_key=settings.sarvam_api_key or "")

    async def translate_text(
        self,
        *,
        text: str,
        source_language_code: str,
        target_language_code: str = "en-IN",
    ) -> str:
        if not self.settings.sarvam_api_key:
            raise ProviderError("SARVAM_API_KEY is not configured.")
        try:
            response = await self._client.text.translate(
                input=text,
                source_language_code=source_language_code,
                target_language_code=target_language_code,
                model=self.settings.sarvam_translation_model,
                mode="formal",
                numerals_format="international",
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Sarvam text translation failed: {exc}") from exc
        return response.translated_text.strip()
