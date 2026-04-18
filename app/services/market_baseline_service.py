from __future__ import annotations

import logging
from statistics import median
from urllib.parse import quote

from playwright.async_api import async_playwright

from app.config import Settings
from app.constants import IPHONE_MODELS
from app.db import Database
from app.models import Offer
from app.scrapers.allegro_lokalnie import AllegroLokalnieScraper
from app.scrapers.olx import OLXScraper
from app.scrapers.vinted import VintedScraper
from app.utils.filters import offer_passes_basic_filters

logger = logging.getLogger(__name__)

STORAGES = ["64GB", "128GB", "256GB", "512GB", "1TB"]


class MarketBaselineService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def refresh_all_baselines(self) -> None:
        logger.info("=== START REFRESH BAZOWYCH CEN ===")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.settings.HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            try:
                for model in IPHONE_MODELS:
                    await self._refresh_model_only(browser, model)
                    for storage in STORAGES:
                        await self._refresh_model_storage(browser, model, storage)
            finally:
                await browser.close()

        logger.info("=== KONIEC REFRESH BAZOWYCH CEN ===")

    async def _refresh_model_only(self, browser, model: str) -> None:
        offers = await self._collect_market_offers(browser, model=model, storage="")
        prices = self._extract_prices_for_exact_match(offers, model, "")

        if len(prices) < self.settings.BASELINE_MIN_SAMPLES_FOR_MODEL:
            logger.info("[baseline] Za mało danych dla model=%s | samples=%s", model, len(prices))
            return

        baseline = self._calculate_baseline(prices)
        if baseline <= 0:
            return

        await self.db.upsert_market_baseline(
            model=model,
            storage="",
            baseline_price=baseline,
            sample_size=len(prices),
            scope="model",
        )
        logger.info("[baseline] model=%s | baseline=%s | samples=%s", model, baseline, len(prices))

    async def _refresh_model_storage(self, browser, model: str, storage: str) -> None:
        offers = await self._collect_market_offers(browser, model=model, storage=storage)
        prices = self._extract_prices_for_exact_match(offers, model, storage)

        if len(prices) < self.settings.BASELINE_MIN_SAMPLES_FOR_STORAGE:
            logger.info("[baseline] Za mało danych dla model=%s storage=%s | samples=%s", model, storage, len(prices))
            return

        baseline = self._calculate_baseline(prices)
        if baseline <= 0:
            return

        await self.db.upsert_market_baseline(
            model=model,
            storage=storage,
            baseline_price=baseline,
            sample_size=len(prices),
            scope="model+storage",
        )
        logger.info("[baseline] model=%s | storage=%s | baseline=%s | samples=%s", model, storage, baseline, len(prices))

    async def _collect_market_offers(self, browser, model: str, storage: str) -> list[Offer]:
        query = f"{model} {storage}".strip()
        offers: list[Offer] = []

        if self.settings.ENABLE_VINTED:
            scraper = VintedScraper(self.settings)
            scraper.start_url = self._build_vinted_url(query)
            offers.extend(await scraper.scrape(browser))

        if self.settings.ENABLE_OLX:
            scraper = OLXScraper(self.settings)
            scraper.start_url = self._build_olx_url(query)
            offers.extend(await scraper.scrape(browser))

        if self.settings.ENABLE_ALLEGRO_LOKALNIE:
            scraper = AllegroLokalnieScraper(self.settings)
            scraper.start_url = self._build_allegro_url(query)
            offers.extend(await scraper.scrape(browser))

        unique: dict[str, Offer] = {}
        filtered: list[Offer] = []

        for offer in offers:
            if not offer.url or offer.url in unique:
                continue
            unique[offer.url] = offer
            if offer_passes_basic_filters(offer, self.settings):
                filtered.append(offer)

        return filtered[: self.settings.BASELINE_MAX_OFFERS_PER_QUERY]

    def _extract_prices_for_exact_match(self, offers: list[Offer], model: str, storage: str) -> list[float]:
        model_norm = model.lower().strip()
        storage_norm = storage.upper().strip()
        prices: list[float] = []

        for offer in offers:
            if offer.price <= 0:
                continue
            if offer.price < self.settings.MIN_PRICE or offer.price > 20000:
                continue
            if (offer.model or "").lower().strip() != model_norm:
                continue
            if storage_norm and (offer.storage or "").upper().strip() != storage_norm:
                continue
            prices.append(float(offer.price))

        return self._remove_outliers(prices)

    def _remove_outliers(self, prices: list[float]) -> list[float]:
        if len(prices) < 6:
            return prices
        sorted_prices = sorted(prices)
        cut = max(1, int(len(sorted_prices) * 0.1))
        trimmed = sorted_prices[cut:-cut]
        return trimmed if trimmed else sorted_prices

    def _calculate_baseline(self, prices: list[float]) -> float:
        if not prices:
            return 0.0
        return round(float(median(prices)), 2)

    def _build_vinted_url(self, query: str) -> str:
        return f"https://www.vinted.pl/catalog?search_text={quote(query)}&order=newest_first&page=1"

    def _build_olx_url(self, query: str) -> str:
        slug = quote(query.replace(" ", "-"))
        return f"https://www.olx.pl/oferty/q-{slug}/?search%5Border%5D=created_at%3Adesc"

    def _build_allegro_url(self, query: str) -> str:
        slug = quote(query)
        return f"https://allegrolokalnie.pl/oferty/q/{slug}?sort=startingTime-desc"
