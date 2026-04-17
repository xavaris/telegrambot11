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
from app.services.translator_service import TranslatorService
from app.utils.filters import offer_passes_basic_filters, is_location_preferred
from app.utils.formatting import build_offer_caption, build_offer_keyboard

logger = logging.getLogger(__name__)


class FlipperService:
    def __init__(self, bot: Bot, db: Database, settings: Settings) -> None:
        self.bot = bot
        self.db = db
        self.settings = settings
        self.translator = TranslatorService(target_lang=settings.TRANSLATE_TO_LANGUAGE)
        self._scan_lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._processing_keys: set[str] = set()

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
        if self._scan_lock.locked():
            logger.warning("Poprzedni scan jeszcze trwa — pomijam kolejne wywołanie.")
            return

        async with self._scan_lock:
            logger.info("=== START SCAN ===")
            self._processing_keys.clear()

            scrapers = self._get_scrapers()
            if not scrapers:
                logger.warning("Brak aktywnych scraperów.")
                return

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
                    tasks = [
                        asyncio.create_task(self._run_single_scraper(scraper, browser))
                        for scraper in scrapers
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for scraper, result in zip(scrapers, results):
                        if isinstance(result, Exception):
                            logger.exception(
                                "Scraper %s zakończył się błędem",
                                scraper.source_name,
                                exc_info=result,
                            )
                        else:
                            logger.info(
                                "Scraper %s zakończył pracę | zebrano=%s",
                                scraper.source_name,
                                result,
                            )
                finally:
                    await browser.close()

            logger.info("=== KONIEC SCAN ===")

    async def _run_single_scraper(self, scraper, browser) -> int:
        logger.info("Start scrapera: %s", scraper.source_name)
        offers = await scraper.scrape(browser, on_offer=self.process_offer)
        logger.info(
            "Koniec scrapera: %s | ofert łącznie=%s",
            scraper.source_name,
            len(offers),
        )
        return len(offers)

    async def process_offer(self, offer: Offer) -> None:
        if not offer.url:
            return

        async with self._process_lock:
            if offer.unique_key in self._processing_keys:
                logger.info("Pomijam duplikat w bieżącym skanie: %s", offer.url)
                return
            self._processing_keys.add(offer.unique_key)

        try:
            logger.info(
                "RAW | source=%s | model=%s | storage=%s | price=%s | title=%s | url=%s",
                offer.source,
                offer.model,
                offer.storage,
                offer.price,
                offer.title,
                offer.url,
            )

            if not offer_passes_basic_filters(offer, self.settings):
                logger.info("FILTER OUT | source=%s | title=%s", offer.source, offer.title)
                return

            if self.settings.ENABLE_TRANSLATION:
                offer.description = self.translator.normalize_description_for_post(offer.description)

            baseline_data = await self.db.get_market_baseline(
                model=offer.model,
                storage=offer.storage,
            )

            if baseline_data:
                baseline_price, sample_size, scope = baseline_data
                offer.market_baseline = baseline_price
                offer.market_sample_size = sample_size
                offer.market_scope = scope

                if baseline_price > 0:
                    offer.score = round((baseline_price - offer.price) / baseline_price, 4)
            else:
                offer.score = 0.0

            if is_location_preferred(offer.location, self.settings):
                offer.score += 0.02

            if offer.score < self.settings.MIN_DEAL_SCORE:
                logger.info(
                    "SCORE OUT | source=%s | score=%s | baseline=%s | title=%s",
                    offer.source,
                    offer.score,
                    offer.market_baseline,
                    offer.title,
                )
                return

            if await self.db.has_seen(offer):
                logger.info("Pomijam seen offer: %s", offer.url)
                return

            logger.info(
                "FILTERED | source=%s | model=%s | storage=%s | price=%s | score=%s | baseline=%s | title=%s",
                offer.source,
                offer.model,
                offer.storage,
                offer.price,
                offer.score,
                offer.market_baseline,
                offer.title,
            )

            await self.publish_offer(offer)
            await self.db.mark_seen(offer)

        except Exception:
            logger.exception("Błąd przy procesowaniu oferty: %s", offer.url)
        finally:
            async with self._process_lock:
                self._processing_keys.discard(offer.unique_key)

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
            "Publikuję ofertę: %s | %s | %s | %.2f",
            offer.source,
            offer.model,
            offer.storage,
            offer.price,
        )

        image_url = (offer.image_url or "").strip()
        has_valid_image = image_url.startswith("http://") or image_url.startswith("https://")

        if has_valid_image:
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

        await self.bot.send_message(
            chat_id=self.settings.CHANNEL_ID,
            text=caption,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=keyboard,
        )
        logger.info("Wysłano przez send_message: %s", offer.url)from __future__ import annotations

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
from app.services.translator_service import TranslatorService
from app.utils.filters import offer_passes_basic_filters, is_location_preferred
from app.utils.formatting import build_offer_caption, build_offer_keyboard

logger = logging.getLogger(__name__)


class FlipperService:
    def __init__(self, bot: Bot, db: Database, settings: Settings) -> None:
        self.bot = bot
        self.db = db
        self.settings = settings
        self.translator = TranslatorService(target_lang=settings.TRANSLATE_TO_LANGUAGE)
        self._scan_lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._processing_keys: set[str] = set()

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
        if self._scan_lock.locked():
            logger.warning("Poprzedni scan jeszcze trwa — pomijam kolejne wywołanie.")
            return

        async with self._scan_lock:
            logger.info("=== START SCAN ===")
            self._processing_keys.clear()

            scrapers = self._get_scrapers()
            if not scrapers:
                logger.warning("Brak aktywnych scraperów.")
                return

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
                    tasks = [
                        asyncio.create_task(self._run_single_scraper(scraper, browser))
                        for scraper in scrapers
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for scraper, result in zip(scrapers, results):
                        if isinstance(result, Exception):
                            logger.exception(
                                "Scraper %s zakończył się błędem",
                                scraper.source_name,
                                exc_info=result,
                            )
                        else:
                            logger.info(
                                "Scraper %s zakończył pracę | zebrano=%s",
                                scraper.source_name,
                                result,
                            )
                finally:
                    await browser.close()

            logger.info("=== KONIEC SCAN ===")

    async def _run_single_scraper(self, scraper, browser) -> int:
        logger.info("Start scrapera: %s", scraper.source_name)
        offers = await scraper.scrape(browser, on_offer=self.process_offer)
        logger.info(
            "Koniec scrapera: %s | ofert łącznie=%s",
            scraper.source_name,
            len(offers),
        )
        return len(offers)

    async def process_offer(self, offer: Offer) -> None:
        if not offer.url:
            return

        async with self._process_lock:
            if offer.unique_key in self._processing_keys:
                logger.info("Pomijam duplikat w bieżącym skanie: %s", offer.url)
                return
            self._processing_keys.add(offer.unique_key)

        try:
            logger.info(
                "RAW | source=%s | model=%s | storage=%s | price=%s | title=%s | url=%s",
                offer.source,
                offer.model,
                offer.storage,
                offer.price,
                offer.title,
                offer.url,
            )

            if not offer_passes_basic_filters(offer, self.settings):
                logger.info("FILTER OUT | source=%s | title=%s", offer.source, offer.title)
                return

            if self.settings.ENABLE_TRANSLATION:
                offer.description = self.translator.normalize_description_for_post(offer.description)

            baseline_data = await self.db.get_market_baseline(
                model=offer.model,
                storage=offer.storage,
            )

            if baseline_data:
                baseline_price, sample_size, scope = baseline_data
                offer.market_baseline = baseline_price
                offer.market_sample_size = sample_size
                offer.market_scope = scope

                if baseline_price > 0:
                    offer.score = round((baseline_price - offer.price) / baseline_price, 4)
            else:
                offer.score = 0.0

            if is_location_preferred(offer.location, self.settings):
                offer.score += 0.02

            if offer.score < self.settings.MIN_DEAL_SCORE:
                logger.info(
                    "SCORE OUT | source=%s | score=%s | baseline=%s | title=%s",
                    offer.source,
                    offer.score,
                    offer.market_baseline,
                    offer.title,
                )
                return

            if await self.db.has_seen(offer):
                logger.info("Pomijam seen offer: %s", offer.url)
                return

            logger.info(
                "FILTERED | source=%s | model=%s | storage=%s | price=%s | score=%s | baseline=%s | title=%s",
                offer.source,
                offer.model,
                offer.storage,
                offer.price,
                offer.score,
                offer.market_baseline,
                offer.title,
            )

            await self.publish_offer(offer)
            await self.db.mark_seen(offer)

        except Exception:
            logger.exception("Błąd przy procesowaniu oferty: %s", offer.url)
        finally:
            async with self._process_lock:
                self._processing_keys.discard(offer.unique_key)

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
            "Publikuję ofertę: %s | %s | %s | %.2f",
            offer.source,
            offer.model,
            offer.storage,
            offer.price,
        )

        image_url = (offer.image_url or "").strip()
        has_valid_image = image_url.startswith("http://") or image_url.startswith("https://")

        if has_valid_image:
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

        await self.bot.send_message(
            chat_id=self.settings.CHANNEL_ID,
            text=caption,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=keyboard,
        )
        logger.info("Wysłano przez send_message: %s", offer.url)