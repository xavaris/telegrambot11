from __future__ import annotations

import logging

from playwright.async_api import Browser

from app.models import Offer
from app.scrapers.base import BaseScraper, OfferCallback
from app.utils.iphone_parser import parse_model, parse_storage, parse_color, parse_condition
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class AllegroLokalnieScraper(BaseScraper):
    source_name = "allegro_lokalnie"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.ALLEGRO_LOKALNIE_SEARCH_URL

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

            cards = page.locator("a[href*='/oferta/'], a[href*='/ogloszenie/']")
            count = min(await cards.count(), self.settings.MAX_OFFERS_PER_SOURCE)
            logger.info("[allegro_lokalnie] Liczba kart: %s", count)

            for i in range(count):
                try:
                    card = cards.nth(i)
                    href = await card.get_attribute("href")
                    url = absolute_url("https://allegrolokalnie.pl", href)
                    raw_text = clean_text(await card.inner_text())

                    if not url:
                        continue

                    title = raw_text.split("zł")[0].strip()[:140] if raw_text else ""
                    price = normalize_price(raw_text)

                    img = ""
                    img_el = card.locator("img").first
                    if await img_el.count():
                        src = (await img_el.get_attribute("src") or "").strip()
                        if src.startswith("http://") or src.startswith("https://"):
                            img = src

                    model = parse_model(title)
                    storage = parse_storage(title)
                    color = parse_color(title)
                    condition = parse_condition(raw_text)

                    offer = Offer(
                        source=self.source_name,
                        title=title,
                        url=url,
                        price=price,
                        location="",
                        image_url=img,
                        description="",
                        condition=condition,
                        model=model,
                        storage=storage,
                        color=color,
                        raw_payload={"raw_card_text": raw_text},
                    )

                    await self.emit_offer(offer, offers, on_offer=on_offer)

                except Exception:
                    logger.exception("[allegro_lokalnie] Nie udało się sparsować karty #%s", i)

            return offers
        finally:
            await self.close_page(page)