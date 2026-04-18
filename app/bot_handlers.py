from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db import Database
from app.services.flipper_service import FlipperService


def setup_handlers(db: Database, flipper: FlipperService) -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "Cześć. Jestem iPhone Flipper Bot.\n"
            "Skanuję OLX, Vinted i Allegro Lokalnie i publikuję okazje."
        )

    @router.message(Command("health"))
    async def cmd_health(message: Message) -> None:
        seen_count = await db.count_seen()
        await message.answer(
            "✅ Bot działa\n"
            f"📦 Zapisane ogłoszenia seen: {seen_count}"
        )

    @router.message(Command("scan_now"))
    async def cmd_scan_now(message: Message) -> None:
        if flipper._scan_lock.locked():
            await message.answer("⏳ Skan już trwa. Poczekaj aż się skończy.")
            return

        await message.answer("🔎 Uruchamiam ręczny skan...")
        await flipper.run_scan()
        await message.answer("✅ Ręczny skan zakończony.")

    return router
