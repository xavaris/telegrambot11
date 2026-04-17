from __future__ import annotations

import logging

from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)


class TranslatorService:
    def __init__(self, target_lang: str = "pl") -> None:
        self.target_lang = target_lang

    def detect_language(self, text: str) -> str:
        text = (text or "").strip()
        if not text or len(text) < 8:
            return "unknown"

        try:
            return detect(text)
        except LangDetectException:
            return "unknown"
        except Exception:
            logger.exception("Błąd wykrywania języka")
            return "unknown"

    def translate_to_polish(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        lang = self.detect_language(text)
        if lang in {"pl", "unknown"}:
            return text

        try:
            translated = GoogleTranslator(source="auto", target="pl").translate(text)
            return (translated or text).strip()
        except Exception:
            logger.exception("Błąd tłumaczenia tekstu")
            return text

    def normalize_description_for_post(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        text = self.translate_to_polish(text)
        text = " ".join(text.split())
        return text[:500]