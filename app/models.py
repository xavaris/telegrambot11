from __future__ import annotations

from dataclasses import dataclass, field
import hashlib


@dataclass(slots=True)
class Offer:
    source: str
    title: str
    url: str
    price: float
    currency: str = "PLN"
    location: str = ""
    image_url: str = ""
    description: str = ""
    condition: str = ""
    model: str = ""
    storage: str = ""
    color: str = ""
    seller_name: str = ""
    score: float = 0.0

    market_baseline: float = 0.0
    market_sample_size: int = 0
    market_scope: str = ""

    raw_payload: dict = field(default_factory=dict)

    @property
    def unique_key(self) -> str:
        base = f"{self.source}|{self.url}".strip().lower()
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
