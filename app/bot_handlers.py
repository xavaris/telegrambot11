from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db import Database

router = Router()


def setup_handlers(db: Database) -> Router:
    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "Cześć. Jestem iPhone Flipper Bot.\n"
            "Działam jako worker i publikuję najlepsze okazje na skonfigurowany kanał/grupę."
        )

    @router.message(Command("health"))
    async def cmd_health(message: Message) -> None:
        seen_count = await db.count_seen()
        await message.answer(f"OK\nseen_offers={seen_count}")

    return router