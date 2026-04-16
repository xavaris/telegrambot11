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

            # Debug: policz wszystkie linki do items
            cards = page.locator("a[href*='/items/']")
            count = await cards.count()
            logger.info("[vinted] Liczba znalezionych kart: %s", count)

            limit = min(count, self.settings.MAX_OFFERS_PER_SOURCE)

            for i in range(limit):
                try:
                    card = cards.nth(i)
                    href = await card.get_attribute("href")
                    url = absolute_url("https://www.vinted.pl", href)
                    card_text = clean_text(await card.inner_text())

                    logger.info("[vinted] CARD #%s | href=%s | text=%s", i, href, card_text[:200])

                    if not url:
                        continue

                    if "iphone" not in card_text.lower():
                        continue

                    img = ""
                    img_el = card.locator("img").first
                    if await img_el.count():
                        img = await img_el.get_attribute("src") or ""

                    title = card_text.split("·")[0].strip() if "·" in card_text else card_text[:120]
                    price = normalize_price(card_text)
                    location = ""

                    model, storage, color, condition = parse_iphone_attributes(title, card_text)

                    offer = Offer(
                        source=self.source_name,
                        title=title or card_text[:120],
                        url=url,
                        price=price,
                        location=location,
                        image_url=img,
                        description="",
                        condition=condition,
                        model=model,
                        storage=storage,
                        color=color,
                        raw_payload={"raw_card_text": card_text},
                    )

                    logger.info(
                        "[vinted] OFFER #%s | model=%s | price=%s | title=%s",
                        i, offer.model, offer.price, offer.title
                    )

                    offers.append(offer)

                except Exception:
                    logger.exception("[vinted] Nie udało się sparsować karty #%s", i)

            logger.info("[vinted] Łącznie ofert po parsowaniu: %s", len(offers))
            return offers

        finally:
            await self.close_page(page)
