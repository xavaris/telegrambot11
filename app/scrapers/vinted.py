from __future__ import annotations

import logging

from playwright.async_api import Browser

from app.models import Offer
from app.scrapers.base import BaseScraper
from app.utils.iphone_parser import parse_iphone_attributes
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class VintedScraper(BaseScraper):
    source_name = "vinted"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.VINTED_SEARCH_URL

    async def scrape(self, browser: Browser) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        try:
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(4000)

            logger.info("[vinted] URL otwarty: %s", self.start_url)
            logger.info("[vinted] Tytuł strony: %s", await page.title())

            cards = page.locator("a[href*='/items/']")
            count = await cards.count()
            logger.info("[vinted] Liczba linków do ofert: %s", count)

            urls: list[str] = []
            for i in range(min(count, self.settings.MAX_OFFERS_PER_SOURCE)):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    url = absolute_url("https://www.vinted.pl", href)
                    if url and url not in urls:
                        urls.append(url)
                except Exception:
                    logger.exception("[vinted] Nie udało się pobrać href dla karty #%s", i)

            logger
