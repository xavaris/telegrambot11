from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import Settings
from app.db import Database
from app.models import Offer
from app.scrapers.allegro_lokalnie import AllegroLokalnieScraper
from app.scrapers.olx import OLXScraper
from app.scrapers.vinted import VintedScraper
from app.services.scoring import calculate_offer_score
from app.utils.filters import offer_passes_basic_filters, is_location_preferred
from app.utils.formatting import build_offer_caption, build_offer_keyboard

logger = logging.getLogger(__name__)


class FlipperService:
    def __init__(self, bot: Bot, db: Database, settings: Settings) -> None:
        self.bot = bot
        self.db = db
        self.settings = settings
        self._lock = asyncio.Lock()

    def _get_scrapers(self):
        scrapers = []
        if self.settings.ENABLE_VINTED:
            scrapers.append(VintedScraper(self.settings))
        if self.settings.ENABLE_OLX:
            scrapers.append(OLXScraper(self.settings))
        if self.settings.ENABLE_ALLEGRO_LOKALNIE:
            scrapers.append(AllegroLokalnieScraper(self.settings))
        return scrapers

    async def run_scan(self) -> None:
        if self._lock.locked():
            logger.warning("Poprzedni scan jeszcze trwa — pomijam kolejne wywołanie.")
            return

        async with self._lock:
            logger.info("=== START SCAN ===")

            offers = await self._collect_offers()
            logger.info("Zebrano ofert: %s", len(offers))

            for offer in offers[:20]:
                logger.info(
                    "RAW | source=%s | model=%s | price=%s | title=%s | image_url=%s",
                    offer.source,
                    offer.model,
                    offer.price,
                    offer.title,
                    offer.image_url,
                )

            filtered = self._filter_and_score(offers)
            logger.info("Po filtrach zostało: %s", len(filtered))

            for offer in filtered[:20]:
                logger.info(
                    "FILTERED | source=%s | model=%s | price=%s | score=%s | title=%s",
                    offer.source,
                    offer.model,
                    offer.price,
                    offer.score,
                    offer.title,
                )

            published = 0
            for offer in filtered:
                if await self.db.has_seen(offer):
                    logger.info("Pomijam seen offer: %s", offer.url)
                    continue

                try:
                    await self.publish_offer(offer)
                    await self.db.mark_seen(offer)
                    published += 1
                except Exception:
                    logger.exception("Nie udało się opublikować oferty: %s", offer.url)

            logger.info("=== KONIEC SCAN | opublikowano=%s ===", published)

    async def _collect_offers(self) -> list[Offer]:
        scrapers = self._get_scrapers()
        if not scrapers:
            logger.warning("Brak aktywnych scraperów.")
            return []

        all_offers: list[Offer] = []

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
                tasks = [scraper.scrape(browser) for scraper in scrapers]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.exception("Scraper zwrócił wyjątek", exc_info=result)
                        continue
                    all_offers.extend(result)

            finally:
                await browser.close()

        # deduplikacja po URL
        unique_by_url: dict[str, Offer] = {}
        for offer in all_offers:
            if offer.url and offer.url not in unique_by_url:
                unique_by_url[offer.url] = offer

        return list(unique_by_url.values())

    def _filter_and_score(self, offers: list[Offer]) -> list[Offer]:
        final: list[Offer] = []

        for offer in offers:
            if not offer_passes_basic_filters(offer, self.settings):
                continue

            offer.score = calculate_offer_score(offer, self.settings.reference_prices)

            # mały bonus za preferowaną lokalizację
            if is_location_preferred(offer.location, self.settings):
                offer.score += 0.02

            if offer.score < self.settings.MIN_DEAL_SCORE:
                continue

            final.append(offer)

        final.sort(key=lambda x: (x.score, -x.price), reverse=True)
        return final

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def publish_offer(self, offer: Offer) -> None:
        caption = build_offer_caption(offer, self.settings)
        keyboard = build_offer_keyboard(offer)

        logger.info(
            "Publikuję ofertę: %s | %s | %.2f",
            offer.source,
            offer.model,
            offer.price,
        )

        image_url = (offer.image_url or "").strip()

        # zdjęcie wysyłamy tylko wtedy, gdy wygląda jak poprawny pełny URL
        if image_url.startswith("http://") or image_url.startswith("https://"):
            try:
                await self.bot.send_photo(
                    chat_id=self.settings.CHANNEL_ID,
                    photo=image_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                logger.info("Wysłano przez send_photo: %s", offer.url)
                return
            except Exception as e:
                logger.exception(
                    "Błąd send_photo dla %s | image_url=%s | error=%s",
                    offer.url,
                    image_url,
                    e,
                )

        # fallback bez zdjęcia
        await self.bot.send_message(
            chat_id=self.settings.CHANNEL_ID,
            text=caption,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=keyboard,
        )
        logger.info("Wysłano przez send_message: %s", offer.url)
