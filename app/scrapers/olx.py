from __future__ import annotations

import logging

from playwright.async_api import Browser

from app.models import Offer
from app.scrapers.base import BaseScraper
from app.utils.iphone_parser import parse_iphone_attributes
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class OLXScraper(BaseScraper):
    source_name = "olx"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.OLX_SEARCH_URL

    async def scrape(self, browser: Browser) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []
        try:
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(2000)

            cards = page.locator("div[data-cy='l-card'], div[data-testid='l-card']")
            count = min(await cards.count(), self.settings.MAX_OFFERS_PER_SOURCE)

            for i in range(count):
                try:
                    card = cards.nth(i)
                    link = card.locator("a[href]").first
                    href = await link.get_attribute("href")
                    url = absolute_url("https://www.olx.pl", href)

                    title = clean_text(await card.locator("h4, h6").first.inner_text()) if await card.locator("h4, h6").count() else ""
                    price_text = clean_text(await card.locator("p[data-testid='ad-price'], p").first.inner_text()) if await card.locator("p").count() else ""
                    location_text = ""
                    location_locator = card.locator("p[data-testid='location-date'], p")
                    if await location_locator.count():
                        all_text = clean_text(await location_locator.last.inner_text())
                        location_text = all_text.split("-")[0].strip()

                    img = ""
                    img_el = card.locator("img").first
                    if await img_el.count():
                        img = await img_el.get_attribute("src") or ""

                    price = normalize_price(price_text)
                    model, storage, color, condition = parse_iphone_attributes(title, "")

                    offers.append(Offer(
                        source=self.source_name,
                        title=title,
                        url=url,
                        price=price,
                        location=location_text,
                        image_url=img,
                        description="",
                        condition=condition,
                        model=model,
                        storage=storage,
                        color=color,
                        raw_payload={"price_text": price_text},
                    ))
                except Exception:
                    logger.exception("[olx] Nie udało się sparsować karty #%s", i)

            return offers
        finally:
            await self.close_page(page)