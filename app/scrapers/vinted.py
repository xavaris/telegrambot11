
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.async_api import Browser, Page

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

    async def scrape(self, browser: Browser, on_offer: OfferCallback | None = None) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        if not self.start_url:
            logger.error("[vinted] Brak start_url")
            await self.close_page(page)
            return []

        try:
            start_url = self._ensure_time_param(self.start_url)
            await self.goto(page, start_url)
            await page.wait_for_timeout(3000)

            cards = page.locator("a[href*='/items/']")
            count = await cards.count()
            logger.info("[vinted] Liczba linków do ofert: %s", count)

            urls: list[str] = []
            for i in range(min(count, self.settings.MAX_OFFERS_PER_SOURCE)):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    url = absolute_url("https://www.vinted.pl", href)
                    if url and "/items/" in url and url not in urls:
                        urls.append(url)
                except Exception:
                    logger.exception("[vinted] Błąd pobrania href dla karty #%s", i)

            for url in urls:
                detail_page = await self._new_page(browser)
                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(1800)

                    title = await self._extract_title(detail_page)
                    price = await self._extract_price(detail_page)
                    image_url = await self._extract_image(detail_page)
                    description = await self._extract_description(detail_page)
                    details = await self._extract_details_map(detail_page)

                    detail_model = clean_text(details.get("model", ""))
                    detail_storage = clean_text(details.get("pamięć", "")) or clean_text(details.get("pamiec", ""))
                    detail_color = clean_text(details.get("kolor", ""))
                    detail_condition = clean_text(details.get("stan", ""))
                    detail_battery = clean_text(details.get("kondycja baterii", ""))
                    location = clean_text(details.get("lokalizacja", ""))

                    model_from_title = parse_model(title)
                    model_from_details = parse_model(detail_model)
                    model = model_from_details or model_from_title
                    if model_from_title and model_from_details and model_from_title != model_from_details:
                        model = model_from_title

                    storage = parse_storage(detail_storage)
                    color = detail_color or parse_color(title)
                    condition = detail_condition or parse_condition(title)

                    final_description = description.strip()
                    if detail_battery:
                        extra = f"Kondycja baterii: {detail_battery}"
                        final_description = f"{final_description}\n{extra}".strip() if final_description else extra

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
                        raw_payload={"details": details},
                    )
                    await self.emit_offer(offer, offers, on_offer=on_offer)
                except Exception:
                    logger.exception("[vinted] Błąd detail page: %s", url)
                finally:
                    await self.close_page(detail_page)
            return offers
        finally:
            await self.close_page(page)

    def _ensure_time_param(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query["time"] = [str(int(time.time()))]
            new_query = urlencode(query, doseq=True)
            return urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url

    async def _extract_title(self, page: Page) -> str:
        json_ld = await self._read_product_json_ld(page)
        if json_ld:
            title = clean_text(json_ld.get("name"))
            if title:
                return title

        selectors = ["h1", "[data-testid='item-page-title']", "meta[property='og:title']"]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue
                value = clean_text(await loc.get_attribute("content")) if selector.startswith("meta") else clean_text(await loc.inner_text())
                if value and len(value) >= 3:
                    return value
            except Exception:
                continue
        return ""

    async def _extract_price(self, page: Page) -> float:
        json_ld = await self._read_product_json_ld(page)
        if json_ld:
            offers = json_ld.get("offers") or {}
            raw = clean_text(offers.get("price"))
            price = normalize_price(raw)
            if 100 <= price <= 15000:
                return price

        selectors = [
            "meta[property='product:price:amount']",
            "[data-testid='item-price']",
            "div[data-testid*='price']",
            "span[data-testid*='price']",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue
                raw = clean_text(await loc.get_attribute("content")) if selector.startswith("meta") else clean_text(await loc.inner_text())
                price = normalize_price(raw)
                if 100 <= price <= 15000:
                    return price
            except Exception:
                continue
        return 0.0

    async def _extract_image(self, page: Page) -> str:
        try:
            meta = page.locator("meta[property='og:image']").first
            if await meta.count():
                content = (await meta.get_attribute("content") or "").strip()
                if content.startswith(("http://", "https://")):
                    return content
        except Exception:
            pass
        return ""

    async def _extract_description(self, page: Page) -> str:
        json_ld = await self._read_product_json_ld(page)
        if json_ld:
            desc = clean_text(json_ld.get("description"))
            if desc and len(desc) >= 3:
                return desc[:500]

        selectors = [
            "[data-testid='item-description']",
            "section[data-testid*='description']",
            "div[data-testid*='description']",
        ]
        bad_snippets = [
            "strona główna", "podobne przedmioty", "podobne rzeczy",
            "ochronę kupujących", "zapytaj", "kup teraz", "zaproponuj cenę",
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
                if any(x in lower_value for x in bad_snippets):
                    continue
                return value[:500]
            except Exception:
                continue
        return ""

    async def _extract_details_map(self, page: Page) -> dict[str, str]:
        details: dict[str, str] = {}

        # Najpierw spróbuj z JSON-LD
        json_ld = await self._read_product_json_ld(page)
        if json_ld:
            # brak gwarancji pełnych pól, więc tylko zapis bezpiecznych
            if json_ld.get("color"):
                details["kolor"] = clean_text(json_ld.get("color"))

        text_candidates: list[str] = []
        selectors = [
            "[data-testid='item-attributes']",
            "[data-testid='item-page-details']",
            "aside",
            "main",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    text = clean_text(await loc.inner_text())
                    if text:
                        text_candidates.append(text)
            except Exception:
                continue

        lines: list[str] = []
        for text in text_candidates:
            parts = [clean_text(x) for x in re.split(r"\n+", text) if clean_text(x)]
            lines.extend(parts)

        deduped_lines = []
        seen = set()
        for line in lines:
            key = line.lower().strip()
            if key not in seen:
                seen.add(key)
                deduped_lines.append(line)
        lines = deduped_lines

        label_variants = {
            "marka": ["Marka", "Brand"],
            "model": ["Model"],
            "pamięć": ["Pamięć", "Pamiec", "Storage"],
            "stan": ["Stan", "Condition"],
            "kolor": ["Kolor", "Color"],
            "kondycja baterii": ["Kondycja baterii", "Battery health"],
            "blokada sim-lock": ["Blokada SIM-lock", "SIM lock"],
            "lokalizacja": ["Lokalizacja", "Location"],
        }
        for canonical_key, variants in label_variants.items():
            for i, line in enumerate(lines[:-1]):
                if line.strip() in variants:
                    value = clean_text(lines[i + 1])
                    if value and len(value) < 120:
                        details[canonical_key] = value
                        break
        return details

    async def _read_product_json_ld(self, page: Page) -> dict:
        try:
            scripts = page.locator("script[type='application/ld+json']")
            count = await scripts.count()
            for i in range(count):
                raw = (await scripts.nth(i).inner_text() or "").strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        except Exception:
            logger.exception("[vinted] Nie udało się odczytać JSON-LD")
        return {}
