from __future__ import annotations

import logging

from playwright.async_api import Browser

from app.models import Offer
from app.scrapers.base import BaseScraper, OfferCallback
from app.utils.iphone_parser import parse_model, parse_storage, parse_color, parse_condition
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class VintedScraper(BaseScraper):
    source_name = "vinted"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.VINTED_SEARCH_URL

    async def scrape(
        self,
        browser: Browser,
        on_offer: OfferCallback | None = None,
    ) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        if not self.start_url:
            logger.error("[vinted] Brak start_url")
            await self.close_page(page)
            return []

        try:
            logger.info("[vinted] start_url=%s", self.start_url)
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(3500)

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

            for idx, url in enumerate(urls):
                detail_page = await self._new_page(browser)

                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(1800)

                    title = await self._extract_title(detail_page)
                    full_text = clean_text(await detail_page.locator("body").inner_text())
                    price = await self._extract_price(detail_page)
                    image_url = await self._extract_image(detail_page)
                    description = await self._extract_description(detail_page)
                    location = self._extract_location_from_text(full_text)
                    details = await self._extract_details_map(detail_page)

                    detail_model = clean_text(details.get("model", ""))
                    detail_storage = clean_text(details.get("pamięć", "")) or clean_text(details.get("pamiec", ""))
                    detail_condition = clean_text(details.get("stan", ""))
                    detail_color = clean_text(details.get("kolor", ""))
                    detail_battery = clean_text(details.get("kondycja baterii", ""))
                    detail_simlock = clean_text(details.get("blokada sim-lock", ""))
                    detail_added = clean_text(details.get("dodane", ""))

                    model = parse_model(detail_model) or parse_model(title)
                    storage = parse_storage(detail_storage) or parse_storage(f"{title} {description}".strip())
                    condition = clean_text(detail_condition) or parse_condition(f"{title} {description}".strip())
                    color = clean_text(detail_color) or parse_color(f"{title} {description}".strip())

                    extra_lines: list[str] = []
                    if detail_battery:
                        extra_lines.append(f"Kondycja baterii: {detail_battery}")
                    if detail_simlock:
                        extra_lines.append(f"SIM-lock: {detail_simlock}")
                    if detail_added:
                        extra_lines.append(f"Dodane: {detail_added}")

                    final_description = (description or "").strip()
                    if extra_lines:
                        extra_text = " | ".join(extra_lines)
                        if final_description:
                            final_description = f"{final_description}\n{extra_text}"
                        else:
                            final_description = extra_text

                    offer = Offer(
                        source=self.source_name,
                        title=title or "Oferta z Vinted",
                        url=url,
                        price=price,
                        location=location,
                        image_url=image_url,
                        description=final_description,
                        condition=condition,
                        model=model,
                        storage=storage,
                        color=color,
                        raw_payload={
                            "full_text": full_text[:2000],
                            "details": details,
                        },
                    )

                    logger.info(
                        "[vinted] DETAIL #%s | model=%s | storage=%s | price=%s | title=%s",
                        idx,
                        model,
                        storage,
                        price,
                        title,
                    )

                    await self.emit_offer(offer, offers, on_offer=on_offer)

                except Exception:
                    logger.exception("[vinted] Błąd podczas parsowania detail page: %s", url)
                finally:
                    await self.close_page(detail_page)

            logger.info("[vinted] Łącznie ofert po detail page: %s", len(offers))
            return offers

        finally:
            await self.close_page(page)

    async def _extract_title(self, page) -> str:
        selectors = [
            "h1",
            "[data-testid='item-page-title']",
            "div[class*='title']",
            "meta[property='og:title']",
        ]

        for selector in selectors:
            try:
                if selector.startswith("meta"):
                    loc = page.locator(selector).first
                    if await loc.count():
                        value = (await loc.get_attribute("content") or "").strip()
                        value = clean_text(value)
                        if value:
                            return value
                else:
                    loc = page.locator(selector).first
                    if await loc.count():
                        value = clean_text(await loc.inner_text())
                        if value:
                            return value
            except Exception:
                continue

        return ""

    async def _extract_price(self, page) -> float:
        selectors = [
            "[data-testid='item-price']",
            "div[class*='price']",
            "span[class*='price']",
            "meta[property='product:price:amount']",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    if selector.startswith("meta"):
                        value = clean_text(await loc.get_attribute("content"))
                    else:
                        value = clean_text(await loc.inner_text())

                    price = normalize_price(value)
                    if 50 <= price <= 20000:
                        return price
            except Exception:
                continue

        return 0.0

    async def _extract_image(self, page) -> str:
        try:
            meta = page.locator("meta[property='og:image']").first
            if await meta.count():
                content = (await meta.get_attribute("content") or "").strip()
                if content.startswith("http://") or content.startswith("https://"):
                    return content
        except Exception:
            pass

        try:
            imgs = page.locator("img")
            img_count = await imgs.count()
            for i in range(min(img_count, 12)):
                src = (await imgs.nth(i).get_attribute("src") or "").strip()
                if not (src.startswith("http://") or src.startswith("https://")):
                    continue

                lowered = src.lower()
                bad_parts = ["avatar", "icon", "logo", "default", "profile", "user"]
                if any(part in lowered for part in bad_parts):
                    continue

                return src
        except Exception:
            pass

        return ""

    async def _extract_description(self, page) -> str:
        selectors = [
            "[data-testid='item-description']",
            "div[class*='description']",
            "section p",
            "section",
        ]

        bad_snippets = [
            "strona główna",
            "przedmioty użytkownika",
            "podobne rzeczy",
            "elektronika",
            "telefony komórkowe",
            "telefony komorkowe",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue

                value = clean_text(await loc.inner_text())
                if not value:
                    continue

                lower_value = value.lower()
                if any(snippet in lower_value for snippet in bad_snippets):
                    continue

                if len(value) > 500:
                    value = value[:500].strip()

                if len(value) < 10:
                    continue

                return value
            except Exception:
                continue

        return ""

    async def _extract_details_map(self, page) -> dict[str, str]:
        details: dict[str, str] = {}

        body_text = clean_text(await page.locator("body").inner_text())
        lines = [line.strip() for line in body_text.split("\n") if line.strip()]

        wanted_keys = {
            "marka",
            "model",
            "kondycja baterii",
            "pamięć",
            "pamiec",
            "stan",
            "blokada sim-lock",
            "kolor",
            "dodane",
        }

        for i in range(len(lines) - 1):
            key = lines[i].lower().strip().rstrip(":")
            value = lines[i + 1].strip()

            if key in wanted_keys and key not in details:
                details[key] = clean_text(value)

        return details

    def _extract_location_from_text(self, full_text: str) -> str:
        lowered = full_text.lower()
        cities = [
            "warszawa", "kraków", "wrocław", "poznań", "gdańsk", "łódź",
            "szczecin", "bydgoszcz", "lublin", "katowice", "gdynia", "sopot"
        ]

        for city in cities:
            if city in lowered:
                return city.title()

        return ""