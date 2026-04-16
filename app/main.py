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
    dp.include_router(setup_handlers(db))

    flipper = FlipperService(bot=bot, db=db, settings=settings)

    scheduler = AsyncIOScheduler(timezone="Europe/Warsaw")
    scheduler.add_job(
        flipper.run_scan,
        trigger=IntervalTrigger(minutes=settings.SCAN_INTERVAL_MINUTES),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        id="scan_job",
    )
    scheduler.start()

    if settings.STARTUP_SCAN:
        asyncio.create_task(flipper.run_scan())

    try:
        logger.info("Bot uruchomiony. Polling start.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())