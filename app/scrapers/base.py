from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Iterable, List

from playwright.async_api import Browser, Page
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import Settings
from app.models import Offer

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    source_name: str = "base"
    start_url: str = ""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    async def scrape(self, browser: Browser) -> list[Offer]:
        raise NotImplementedError

    async def _new_page(self, browser: Browser) -> Page:
        context = await browser.new_context(
            user_agent=self.settings.USER_AGENT,
            locale="pl-PL",
            java_script_enabled=True,
            viewport={"width": 1440, "height": 2400},
        )
        page = await context.new_page()
        page.set_default_timeout(self.settings.PLAYWRIGHT_TIMEOUT_MS)
        return page

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def goto(self, page: Page, url: str) -> None:
        logger.info("[%s] Otwieram URL: %s", self.source_name, url)
        await page.goto(url, wait_until="domcontentloaded", timeout=self.settings.PLAYWRIGHT_TIMEOUT_MS)
        await page.wait_for_timeout(self.settings.REQUEST_DELAY_MS)

    async def close_page(self, page: Page) -> None:
        try:
            await page.context.close()
        except Exception:
            logger.exception("[%s] Błąd przy zamykaniu contextu", self.source_name)