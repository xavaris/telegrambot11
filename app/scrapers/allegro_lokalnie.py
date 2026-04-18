from __future__ import annotations

import logging

from playwright.async_api import Browser, Page

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

    async def scrape(self, browser: Browser, on_offer: OfferCallback | None = None) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        try:
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(1800)

            cards = page.locator("a[href*='/oferta/'], a[href*='/ogloszenie/']")
            count = min(await cards.count(), self.settings.MAX_OFFERS_PER_SOURCE)
            logger.info("[allegro_lokalnie] Liczba kart: %s", count)

            urls: list[str] = []
            for i in range(count):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    url = absolute_url("https://allegrolokalnie.pl", href)
                    if url and url not in urls:
                        urls.append(url)
                except Exception:
                    logger.exception("[allegro_lokalnie] Nie udało się pobrać URL-a #%s", i)

            for i, url in enumerate(urls):
                detail_page = await self._new_page(browser)
                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(1200)
                    offer = await self._extract_detail_offer(detail_page, url)
                    if offer:
                        await self.emit_offer(offer, offers, on_offer=on_offer)
                except Exception:
                    logger.exception("[allegro_lokalnie] Nie udało się sparsować detail page #%s: %s", i, url)
                finally:
                    await self.close_page(detail_page)

            return offers
        finally:
            await self.close_page(page)

    async def _extract_detail_offer(self, page: Page, url: str) -> Offer | None:
        title = await self._pick_text(page, ["h1", "meta[property='og:title']"])
        body_text = clean_text(await page.locator("body").inner_text())
        description = await self._pick_text(page, [
            "[data-testid='description']",
            "div[class*='description']",
            "section",
        ])
        price = await self._extract_price(page)
        location = await self._extract_location(page, body_text)
        image = await self._extract_image(page)

        blob = " ".join(x for x in [title, description, body_text[:1000]] if x)
        model = parse_model(blob)
        storage = parse_storage(blob)
        color = parse_color(blob)
        condition = parse_condition(blob)

        if not title:
            return None

        return Offer(
            source=self.source_name,
            title=title,
            url=url,
            price=price,
            location=location,
            image_url=image,
            description=description[:700],
            condition=condition,
            model=model,
            storage=storage,
            color=color,
            raw_payload={"body_text": body_text[:2000]},
        )

    async def _pick_text(self, page: Page, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue
                if selector.startswith("meta"):
                    val = clean_text(await loc.get_attribute("content"))
                else:
                    val = clean_text(await loc.inner_text())
                if val:
                    return val
            except Exception:
                continue
        return ""

    async def _extract_price(self, page: Page) -> float:
        selectors = ["[data-testid='price']","h2","h3","meta[property='product:price:amount']"]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    value = await loc.get_attribute("content") if selector.startswith("meta") else await loc.inner_text()
                    price = normalize_price(value, min_price=100, max_price=20000)
                    if price:
                        return price
            except Exception:
                continue
        return 0.0

    async def _extract_location(self, page: Page, body_text: str) -> str:
        selectors = ["[data-testid='location']","[data-testid='seller-location']"]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    value = clean_text(await loc.inner_text())
                    if value:
                        return value
            except Exception:
                continue
        return body_text[:80]

    async def _extract_image(self, page: Page) -> str:
        try:
            meta = page.locator("meta[property='og:image']").first
            if await meta.count():
                content = (await meta.get_attribute("content") or "").strip()
                if content.startswith("http://") or content.startswith("https://"):
                    return content
        except Exception:
            pass
        return ""
