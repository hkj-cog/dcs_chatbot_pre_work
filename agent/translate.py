# Google Cloud Translation API v2 wrapper — language detection and text translation
from typing import Optional

from google.cloud import translate_v2 as translate

from libs.logger import logger


class Translator:
    """Language detection and translation via Google Cloud Translation API."""

    _translate_client: Optional[translate.Client] = None

    # Lazy singleton initialiser for the Cloud Translation v2 client
    @classmethod
    def _get_client(cls) -> translate.Client:
        if cls._translate_client is None:
            cls._translate_client = translate.Client()
        return cls._translate_client

    # Returns the BCP-47 language code detected by the Cloud Translation API
    @classmethod
    def detect_language(cls, text):
        if isinstance(text, bytes):
            text = text.decode("utf-8")

        result = cls._get_client().detect_language(text)
        return result["language"]

    @classmethod
    def detect_language_with_confidence(cls, text) -> tuple[str, float]:
        """Returns (language_code, confidence). Confidence defaults to 1.0 when not in API response."""
        if isinstance(text, bytes):
            text = text.decode("utf-8")

        result = cls._get_client().detect_language(text)
        return result["language"], float(result.get("confidence", 1.0))

    @classmethod
    def translate(cls, question, answer):
        """Translates answer into the question's language. Returns (was_translated, text)."""
        question_language = Translator.detect_language(question)
        answer_language = Translator.detect_language(answer)

        text = answer
        try:
            if question_language != answer_language:
                if isinstance(text, bytes):
                    text = [text.decode("utf-8")]
                elif isinstance(text, str):
                    text = [text]

                results = cls._get_client().translate(
                    values=text,
                    target_language=question_language,
                    source_language=answer_language,
                )

                translated_text = answer
                for result in results:
                    logger.info(
                        f"Translation — detected: {result.get('detectedSourceLanguage', 'n/a')} "
                        f"content_length={len(result.get('input', ''))}"
                    )
                    translated_text = result["translatedText"]
                return True, translated_text
        except Exception as e:
            logger.warning(f"Translation failed for session (non-fatal): {e}")

        return False, answer
