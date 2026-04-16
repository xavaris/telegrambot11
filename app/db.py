from __future__ import annotations

import aiosqlite
import logging
from typing import Optional

from app.models import Offer

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seen_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unique_key TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    price REAL,
                    model TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_seen_offers_source
                ON seen_offers (source)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_seen_offers_created_at
                ON seen_offers (created_at)
            """)
            await db.commit()
        logger.info("Baza danych gotowa: %s", self.db_path)

    async def has_seen(self, offer: Offer) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM seen_offers WHERE unique_key = ? LIMIT 1",
                (offer.unique_key,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return row is not None

    async def mark_seen(self, offer: Offer) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR IGNORE INTO seen_offers (
                    unique_key, source, url, title, price, model
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                offer.unique_key,
                offer.source,
                offer.url,
                offer.title,
                offer.price,
                offer.model,
            ))
            await db.commit()

    async def count_seen(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM seen_offers")
            row = await cursor.fetchone()
            await cursor.close()
            return int(row[0] if row else 0)