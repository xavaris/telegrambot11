from __future__ import annotations

import logging

from playwright.async_api import Browser, Page

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

    async def scrape(self, browser: Browser, on_offer: OfferCallback | None = None) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        try:
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(1800)

            cards = page.locator("div[data-cy='l-card'], div[data-testid='l-card']")
            count = min(await cards.count(), self.settings.MAX_OFFERS_PER_SOURCE)
            logger.info("[olx] Liczba kart: %s", count)

            urls: list[str] = []
            for i in range(count):
                try:
                    card = cards.nth(i)
                    link = card.locator("a[href]").first
                    href = await link.get_attribute("href")
                    url = absolute_url("https://www.olx.pl", href)
                    if url and url not in urls:
                        urls.append(url)
                except Exception:
                    logger.exception("[olx] Nie udało się pobrać URL-a karty #%s", i)

            for i, url in enumerate(urls):
                detail_page = await self._new_page(browser)
                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(1200)
                    offer = await self._extract_detail_offer(detail_page, url)
                    if offer:
                        await self.emit_offer(offer, offers, on_offer=on_offer)
                except Exception:
                    logger.exception("[olx] Nie udało się sparsować detail page #%s: %s", i, url)
                finally:
                    await self.close_page(detail_page)

            return offers
        finally:
            await self.close_page(page)

    async def _extract_detail_offer(self, page: Page, url: str) -> Offer | None:
        title = await self._pick_text(page, ["h1", "[data-cy='ad_title']", "[data-testid='offer_title']"])
        full_text = clean_text(await page.locator("body").inner_text())
        description = await self._extract_description(page)
        price = await self._extract_price(page)
        location = await self._extract_location(page, full_text)
        image = await self._extract_image(page)

        blob = " ".join(x for x in [title, description, full_text[:1000]] if x)
        model = parse_model(blob)
        storage = parse_storage(blob)
        color = parse_color(blob)
        condition = parse_condition(blob)

        if not title or not url:
            return None

        return Offer(
            source=self.source_name,
            title=title,
            url=url,
            price=price,
            location=location,
            image_url=image,
            description=description,
            condition=condition,
            model=model,
            storage=storage,
            color=color,
            raw_payload={"full_text": full_text[:2000]},
        )

    async def _pick_text(self, page: Page, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    text = clean_text(await loc.inner_text())
                    if text:
                        return text
            except Exception:
                continue
        return ""

    async def _extract_price(self, page: Page) -> float:
        selectors = [
            "h3",
            "[data-testid='ad-price-container']",
            "[data-testid='offer-price']",
            "div[data-testid='price-box']",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    price = normalize_price(await loc.inner_text(), min_price=100, max_price=20000)
                    if price:
                        return price
            except Exception:
                continue
        return 0.0

    async def _extract_description(self, page: Page) -> str:
        selectors = [
            "[data-cy='ad_description']",
            "[data-testid='description-content']",
            "div[data-testid='text']",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    text = clean_text(await loc.inner_text())
                    if text and len(text) >= 10:
                        return text[:700]
            except Exception:
                continue
        return ""

    async def _extract_location(self, page: Page, full_text: str) -> str:
        selectors = [
            "[data-testid='location-date']",
            "[data-testid='map-link']",
            "div:has-text('Lokalizacja')",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    text = clean_text(await loc.inner_text())
                    if text:
                        return text.split("-")[0].strip()
            except Exception:
                continue
        lines = [x.strip() for x in full_text.split("  ") if x.strip()]
        return lines[0][:80] if lines else ""

    async def _extract_image(self, page: Page) -> str:
        selectors = [
            "meta[property='og:image']",
            "img[src^='https://']",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    if selector.startswith("meta"):
                        src = (await loc.get_attribute("content") or "").strip()
                    else:
                        src = (await loc.get_attribute("src") or "").strip()
                    if src.startswith("http://") or src.startswith("https://"):
                        return src
            except Exception:
                continue
        return ""
