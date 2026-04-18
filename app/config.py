
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    TELEGRAM_TOKEN: str
    CHANNEL_ID: str
    MESSAGE_THREAD_ID: int | None = None

    SCAN_INTERVAL_MINUTES: int = 15
    STARTUP_SCAN: bool = True

    DATABASE_PATH: str = "/app/data/offers.db"
    LOG_LEVEL: str = "INFO"

    HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT_MS: int = 30000
    MAX_OFFERS_PER_SOURCE: int = 20
    REQUEST_DELAY_MS: int = 800
    USER_AGENT: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    ONLY_MODELS: str = ""
    EXCLUDED_KEYWORDS: str = (
        "icloud,blokada,na części,na czesci,uszkodzony,zbity,bez face id,"
        "etui,case,pokrowiec,szkło,szklo,ładowarka,ladowarka,kabel,"
        "pudełko,pudelko,karton,box,obudowa,plecki,wyświetlacz,wyswietlacz,"
        "bateria,taśma,tasma"
    )
    PREFERRED_LOCATIONS: str = ""
    PREFERRED_REGIONS: str = ""

    MIN_DEAL_SCORE: float = 0.00
    MIN_PRICE: float = 250
    MAX_PRICE: float = 10000
    MAX_PRICE_BY_MODEL_JSON: str = "{}"

    ENABLE_VINTED: bool = True
    ENABLE_OLX: bool = True
    ENABLE_ALLEGRO_LOKALNIE: bool = True

    VINTED_SEARCH_URL: str = "https://www.vinted.pl/catalog?search_text=iphone"
    OLX_SEARCH_URL: str = "https://www.olx.pl/oferty/q-iphone/"
    ALLEGRO_LOKALNIE_SEARCH_URL: str = "https://allegrolokalnie.pl/oferty/q/iphone"

    ENABLE_TRANSLATION: bool = True
    TRANSLATE_TO_LANGUAGE: str = "pl"

    ENABLE_MARKET_BASELINE_REFRESH: bool = True
    BASELINE_REFRESH_INTERVAL_HOURS: int = 24
    BASELINE_MAX_OFFERS_PER_QUERY: int = 50
    BASELINE_MIN_SAMPLES_FOR_STORAGE: int = 5
    BASELINE_MIN_SAMPLES_FOR_MODEL: int = 8

    @field_validator("SCAN_INTERVAL_MINUTES")
    @classmethod
    def validate_scan_interval(cls, value: int) -> int:
        if value < 1:
            raise ValueError("SCAN_INTERVAL_MINUTES musi być >= 1")
        return value

    @property
    def only_models_list(self) -> List[str]:
        return [x.strip().lower() for x in self.ONLY_MODELS.split(",") if x.strip()]

    @property
    def excluded_keywords_list(self) -> List[str]:
        return [x.strip().lower() for x in self.EXCLUDED_KEYWORDS.split(",") if x.strip()]

    @property
    def preferred_locations_list(self) -> List[str]:
        return [x.strip().lower() for x in self.PREFERRED_LOCATIONS.split(",") if x.strip()]

    @property
    def preferred_regions_list(self) -> List[str]:
        return [x.strip().lower() for x in self.PREFERRED_REGIONS.split(",") if x.strip()]

    @property
    def max_price_by_model(self) -> Dict[str, float]:
        try:
            data = json.loads(self.MAX_PRICE_BY_MODEL_JSON or "{}")
            return {str(k).lower(): float(v) for k, v in data.items()}
        except Exception:
            return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
