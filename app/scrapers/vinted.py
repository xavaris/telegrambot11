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

            logger.info("[vinted] Unikalnych URL-i do sprawdzenia: %s", len(urls))

            for idx, url in enumerate(urls[: self.settings.MAX_OFFERS_PER_SOURCE]):
                detail_page = await self._new_page(browser)

                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(2500)

                    title = ""
                    for selector in [
                        "h1",
                        "[data-testid='item-page-title']",
                        "div[class*='title']",
                    ]:
                        loc = detail_page.locator(selector).first
                        if await loc.count():
                            value = clean_text(await loc.inner_text())
                            if value:
                                title = value
                                break

                    full_text = clean_text(await detail_page.locator("body").inner_text())

                    price = 0.0
                    for selector in [
                        "[data-testid='item-price']",
                        "div[class*='price']",
                        "span[class*='price']",
                    ]:
                        loc = detail_page.locator(selector).first
                        if await loc.count():
                            price_text = clean_text(await loc.inner_text())
                            price = normalize_price(price_text)
                            if price > 0:
                                break

                    if price <= 0:
                        price = normalize_price(full_text)

                    image_url = ""
                    imgs = detail_page.locator("img")
                    img_count = await imgs.count()
                    for j in range(min(img_count, 8)):
                        src = await imgs.nth(j).get_attribute("src")
                        src = (src or "").strip()
                        if src.startswith("http://") or src.startswith("https://"):
                            image_url = src
                            break

                    description = ""
                    for selector in [
                        "[data-testid='item-description']",
                        "div[class*='description']",
                        "section",
                    ]:
                        loc = detail_page.locator(selector).first
                        if await loc.count():
                            value = clean_text(await loc.inner_text())
                            if value and len(value) > 20:
                                description = value[:500]
                                break

                    location = ""
                    for possible in [
                        "warszawa",
                        "kraków",
                        "wrocław",
                        "poznań",
                        "gdańsk",
                        "łódź",
                    ]:
                        if possible in full_text.lower():
                            location = possible.title()
                            break

                    model, storage, color, condition = parse_iphone_attributes(
                        title, description or full_text
                    )

                    logger.info(
                        "[vinted] DETAIL #%s | model=%s | price=%s | title=%s | url=%s",
                        idx,
                        model,
                        price,
                        title,
                        url,
                    )

                    offers.append(
                        Offer(
                            source=self.source_name,
                            title=title or "Oferta z Vinted",
                            url=url,
                            price=price,
                            location=location,
                            image_url=image_url,
                            description=description,
                            condition=condition,
                            model=model,
                            storage=storage,
                            color=color,
                            raw_payload={"full_text": full_text[:2000]},
                        )
                    )

                except Exception:
                    logger.exception("[vinted] Błąd podczas parsowania detail page: %s", url)
                finally:
                    await self.close_page(detail_page)

            logger.info("[vinted] Łącznie ofert po detail page: %s", len(offers))
            return offers

        finally:
            await self.close_page(page)
