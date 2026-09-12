from services.exchange_rates import fallback_exchange_rate
from services.search_price_source import (
    SEARCH_PRICE_SOURCE_CARDMARKET,
    SEARCH_PRICE_SOURCE_PRICECHARTING,
    SEARCH_PRICE_SOURCE_TCGPLAYER,
    normalize_search_price_source,
)

VALID_PRICE_FIELDS = {"price_market", "price_trend", "price_avg1", "price_avg7", "price_avg30", "price_low"}
PRICE_PRIMARY_TO_FIELD = {
    "market": "price_market",
    "avg": "price_market",
    "trend": "price_trend",
    "avg1": "price_avg1",
    "avg7": "price_avg7",
    "avg30": "price_avg30",
    "low": "price_low",
}
REVERSE_HOLO_VARIANTS = {"Reverse Holo"}
HOLO_VARIANTS = {"Holo"}
HOLO_FIELD_MAP = {
    "price_market": "price_market_holo",
    "price_trend": "price_trend_holo",
    "price_avg1": "price_avg1_holo",
    "price_avg7": "price_avg7_holo",
    "price_avg30": "price_avg30_holo",
    "price_low": "price_low_holo",
}


def normalize_price_field(price_field: str | None) -> str:
    if not price_field:
        return "price_trend"
    value = str(price_field)
    field = PRICE_PRIMARY_TO_FIELD.get(value, value)
    return field if field in VALID_PRICE_FIELDS else "price_trend"


def usd_to_eur_rate(usd_to_eur: float | None = None) -> float:
    if usd_to_eur is not None:
        try:
            rate = float(usd_to_eur)
        except (TypeError, ValueError):
            rate = 0
        if rate > 0:
            return rate
    return fallback_exchange_rate("USD", "EUR")


def _positive_price(value) -> float | None:
    """Return a usable price, treating missing/zero values as unavailable."""
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _first_positive(*values) -> float:
    for value in values:
        price = _positive_price(value)
        if price is not None:
            return price
    return 0


def tcgplayer_market_price(card, variant=None) -> float:
    """Return the best TCGPlayer USD market price for a print variant."""
    if not card:
        return 0
    normal = getattr(card, "price_tcg_normal_market", None)
    holo = getattr(card, "price_tcg_holo_market", None)
    reverse = getattr(card, "price_tcg_reverse_market", None)
    if variant in REVERSE_HOLO_VARIANTS:
        return _first_positive(reverse, holo, normal)
    if variant in HOLO_VARIANTS:
        return _first_positive(holo, normal, reverse)
    return _first_positive(normal, holo, reverse)


def _cardmarket_price(card, variant, price_field: str) -> float:
    field = normalize_price_field(price_field)
    if variant in REVERSE_HOLO_VARIANTS:
        holo_field = HOLO_FIELD_MAP.get(field)
        return _first_positive(
            getattr(card, holo_field, None) if holo_field else None,
            getattr(card, field, None),
            getattr(card, "price_market_holo", None),
            getattr(card, "price_market", None),
        )
    return _first_positive(getattr(card, field, None), getattr(card, "price_market", None))


def effective_market_price(
    card,
    variant=None,
    price_field: str | None = "price_trend",
    price_source: str | None = SEARCH_PRICE_SOURCE_CARDMARKET,
    usd_to_eur: float | None = None,
) -> float:
    """Return the selected market price as EUR.

    Cardmarket values are already EUR. TCGPlayer and PriceCharting ungraded
    prices are USD and converted so portfolio totals, PnL, and ``formatPrice``
    keep a single currency. PriceCharting falls back to TCGPlayer when the
    ungraded cache is empty so owned cards are not valued at zero.
    """
    if not card:
        return 0
    source = normalize_search_price_source(price_source)
    if source == SEARCH_PRICE_SOURCE_PRICECHARTING:
        usd = _first_positive(
            getattr(card, "price_pc_ungraded", None),
            tcgplayer_market_price(card, variant),
        )
        return usd * usd_to_eur_rate(usd_to_eur) if usd else 0
    if source == SEARCH_PRICE_SOURCE_TCGPLAYER:
        usd = tcgplayer_market_price(card, variant)
        return usd * usd_to_eur_rate(usd_to_eur) if usd else 0
    return _cardmarket_price(card, variant, price_field)
