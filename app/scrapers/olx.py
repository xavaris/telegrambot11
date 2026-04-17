from __future__ import annotations

import logging

from playwright.async_api import Browser

from app.models import Offer
from app.scrapers.base import BaseScraper, OfferCallback
from app.utils.iphone_parser import parse_model, parse_storage, parse_color, parse_condition
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class OLXScraper(BaseScraper):
    source_name = "olx"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.OLX_SEARCH_URL

    async def scrape(
        self,
        browser: Browser,
        on_offer: OfferCallback | None = None,
    ) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        try:
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(2000)

            cards = page.locator("div[data-cy='l-card'], div[data-testid='l-card']")
            count = min(await cards.count(), self.settings.MAX_OFFERS_PER_SOURCE)
            logger.info("[olx] Liczba kart: %s", count)

            for i in range(count):
                try:
                    card = cards.nth(i)
                    link = card.locator("a[href]").first
                    href = await link.get_attribute("href")
                    url = absolute_url("https://www.olx.pl", href)

                    title = ""
                    title_loc = card.locator("h4, h6").first
                    if await title_loc.count():
                        title = clean_text(await title_loc.inner_text())

                    price_text = ""
                    price_loc = card.locator("p[data-testid='ad-price'], p").first
                    if await price_loc.count():
                        price_text = clean_text(await price_loc.inner_text())

                    location_text = ""
                    location_locator = card.locator("p[data-testid='location-date'], p")
                    if await location_locator.count():
                        all_text = clean_text(await location_locator.last.inner_text())
                        location_text = all_text.split("-")[0].strip()

                    img = ""
                    img_el = card.locator("img").first
                    if await img_el.count():
                        src = (await img_el.get_attribute("src") or "").strip()
                        if src.startswith("http://") or src.startswith("https://"):
                            img = src

                    price = normalize_price(price_text)

                    model = parse_model(title)
                    storage = parse_storage(title)
                    color = parse_color(title)
                    condition = parse_condition(title)

                    offer = Offer(
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
                    )

                    await self.emit_offer(offer, offers, on_offer=on_offer)

                except Exception:
                    logger.exception("[olx] Nie udało się sparsować karty #%s", i)

            return offers
        finally:
            await self.close_page(page)