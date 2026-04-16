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
                    storage TEXT,
                    condition TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS market_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model TEXT NOT NULL,
                    storage TEXT NOT NULL DEFAULT '',
                    baseline_price REAL NOT NULL,
                    sample_size INTEGER NOT NULL,
                    scope TEXT NOT NULL,
                    refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(model, storage)
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_seen_offers_unique_key
                ON seen_offers (unique_key)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_market_baselines_model_storage
                ON market_baselines (model, storage)
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
                    unique_key, source, url, title, price, model, storage, condition
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                offer.unique_key,
                offer.source,
                offer.url,
                offer.title,
                offer.price,
                offer.model,
                offer.storage,
                offer.condition,
            ))
            await db.commit()

    async def upsert_market_baseline(
        self,
        model: str,
        storage: str,
        baseline_price: float,
        sample_size: int,
        scope: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO market_baselines (
                    model, storage, baseline_price, sample_size, scope, refreshed_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(model, storage) DO UPDATE SET
                    baseline_price = excluded.baseline_price,
                    sample_size = excluded.sample_size,
                    scope = excluded.scope,
                    refreshed_at = CURRENT_TIMESTAMP
            """, (
                model.lower().strip(),
                storage.upper().strip(),
                baseline_price,
                sample_size,
                scope,
            ))
            await db.commit()

    async def get_market_baseline(
        self,
        model: str,
        storage: str,
    ) -> tuple[float, int, str] | None:
        model_norm = model.lower().strip()
        storage_norm = storage.upper().strip()

        async with aiosqlite.connect(self.db_path) as db:
            # Najpierw dokładny model + storage
            if storage_norm:
                cursor = await db.execute("""
                    SELECT baseline_price, sample_size, scope
                    FROM market_baselines
                    WHERE model = ? AND storage = ?
                    LIMIT 1
                """, (model_norm, storage_norm))
                row = await cursor.fetchone()
                await cursor.close()

                if row:
                    return float(row[0]), int(row[1]), str(row[2])

            # Fallback do samego modelu
            cursor = await db.execute("""
                SELECT baseline_price, sample_size, scope
                FROM market_baselines
                WHERE model = ? AND storage = ''
                LIMIT 1
            """, (model_norm,))
            row = await cursor.fetchone()
            await cursor.close()

            if row:
                return float(row[0]), int(row[1]), str(row[2])

        return None

    async def clear_market_baselines(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM market_baselines")
            await db.commit()