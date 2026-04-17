from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.bot_handlers import setup_handlers
from app.config import get_settings
from app.db import Database
from app.logging_setup import setup_logging
from app.services.flipper_service import FlipperService
from app.services.market_baseline_service import MarketBaselineService

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    os.makedirs(os.path.dirname(settings.DATABASE_PATH), exist_ok=True)

    setup_logging(settings.LOG_LEVEL)
    logger.info("Start aplikacji...")

    db = Database(settings.DATABASE_PATH)
    await db.init()

    bot = Bot(token=settings.TELEGRAM_TOKEN)
    dp = Dispatcher()

    flipper = FlipperService(bot=bot, db=db, settings=settings)
    baseline_service = MarketBaselineService(db=db, settings=settings)

    dp.include_router(setup_handlers(db, flipper))

    scheduler = AsyncIOScheduler(timezone="Europe/Warsaw")

    scheduler.add_job(
        flipper.run_scan,
        trigger=IntervalTrigger(minutes=settings.SCAN_INTERVAL_MINUTES),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        id="scan_job",
    )

    if settings.ENABLE_MARKET_BASELINE_REFRESH:
        scheduler.add_job(
            baseline_service.refresh_all_baselines,
            trigger=IntervalTrigger(hours=settings.BASELINE_REFRESH_INTERVAL_HOURS),
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
            id="baseline_refresh_job",
        )

    scheduler.start()

    if settings.STARTUP_SCAN:
        asyncio.create_task(flipper.run_scan())

    if settings.ENABLE_MARKET_BASELINE_REFRESH:
        asyncio.create_task(baseline_service.refresh_all_baselines())

    try:
        logger.info("Bot uruchomiony. Polling start.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())