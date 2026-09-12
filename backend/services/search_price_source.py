"""Search-page market price source setting."""

from __future__ import annotations

from typing import Optional

SEARCH_PRICE_SOURCE_KEY = "search_price_source"
SEARCH_PRICE_SOURCE_CARDMARKET = "cardmarket"
SEARCH_PRICE_SOURCE_TCGPLAYER = "tcgplayer"
SEARCH_PRICE_SOURCE_PRICECHARTING = "pricecharting"
SEARCH_PRICE_SOURCES = frozenset({
    SEARCH_PRICE_SOURCE_CARDMARKET,
    SEARCH_PRICE_SOURCE_TCGPLAYER,
    SEARCH_PRICE_SOURCE_PRICECHARTING,
})
DEFAULT_SEARCH_PRICE_SOURCE = SEARCH_PRICE_SOURCE_CARDMARKET


def normalize_search_price_source(value: Optional[str]) -> str:
    """Return a supported search price source, defaulting to Cardmarket."""
    if value is None:
        return DEFAULT_SEARCH_PRICE_SOURCE
    normalized = str(value).strip().lower()
    if normalized not in SEARCH_PRICE_SOURCES:
        return DEFAULT_SEARCH_PRICE_SOURCE
    return normalized


def parse_search_price_source(value) -> str:
    """Validate a user-supplied search price source or raise ValueError."""
    normalized = str(value).strip().lower()
    if normalized not in SEARCH_PRICE_SOURCES:
        allowed = ", ".join(sorted(SEARCH_PRICE_SOURCES))
        raise ValueError(f"search_price_source must be one of: {allowed}")
    return normalized


def get_search_price_source(db, user_id: int) -> str:
    """Read the current user's search price source from user_settings."""
    from models import UserSetting

    row = (
        db.query(UserSetting)
        .filter(
            UserSetting.user_id == user_id,
            UserSetting.key == SEARCH_PRICE_SOURCE_KEY,
        )
        .first()
    )
    return normalize_search_price_source(row.value if row else None)
