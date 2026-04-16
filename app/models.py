from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
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
    raw_payload: dict = field(default_factory=dict)

    @property
    def unique_key(self) -> str:
        base = f"{self.source}|{self.url}".strip().lower()
        return hashlib.sha256(base.encode("utf-8")).hexdigest()