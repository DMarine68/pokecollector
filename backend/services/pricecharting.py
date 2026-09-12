"""Service for retrieving PriceCharting card pricing and graded price comparisons."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple
from sqlalchemy.orm import Session

from models import Binder, BinderCard, Card, CollectionItem, User, UserSetting, WishlistItem
from services.price_utils import is_valid_price
from services.search_price_source import (
    SEARCH_PRICE_SOURCE_KEY,
    SEARCH_PRICE_SOURCE_PRICECHARTING,
    normalize_search_price_source,
)

PRICECHARTING_SEARCH_STALE = datetime.timedelta(hours=24)
PRICECHARTING_MIN_INTERVAL_SECONDS = 1.05

logger = logging.getLogger(__name__)

# Cache in-memory: card_id -> (timestamp, data_dict)
_PRICECHARTING_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour

_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT: Optional[float] = None


def clean_card_number(raw_num: Optional[str]) -> str:
    """Normalize card numbers for search, e.g. '111/197' -> '111', '025/165' -> '25'."""
    if not raw_num:
        return ""
    num = str(raw_num).strip()
    if "/" in num:
        num = num.split("/")[0].strip()
    if num.isdigit():
        return str(int(num))
    return num


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug for PriceCharting URLs."""
    text = text.lower().strip()
    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def build_pricecharting_urls(
    card_name: str,
    card_number: Optional[str],
    set_name: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (search_url, direct_url) for a card on PriceCharting."""
    clean_num = clean_card_number(card_number)
    query_parts = [card_name]
    if clean_num:
        query_parts.append(clean_num)
    query = " ".join(query_parts)
    search_url = f"https://www.pricecharting.com/search-products?type=prices&q={urllib.parse.quote_plus(query)}"

    clean_set = set_name or ""
    if clean_set and not clean_set.lower().startswith("pokemon"):
        clean_set = f"Pokemon {clean_set}".strip()
    elif not clean_set:
        clean_set = "Pokemon"

    set_slug = _slugify(clean_set)
    card_slug = _slugify(card_name)
    num_slug = f"-{clean_num}" if clean_num else ""
    direct_url = f"https://www.pricecharting.com/game/{set_slug}/{card_slug}{num_slug}"
    return search_url, direct_url


def throttle_pricecharting_request(min_interval: float = PRICECHARTING_MIN_INTERVAL_SECONDS) -> None:
    """Block until at least ``min_interval`` seconds have passed since the last PriceCharting HTTP call."""
    global _LAST_REQUEST_AT
    wait_for = 0.0
    with _REQUEST_LOCK:
        now = time.monotonic()
        last = _LAST_REQUEST_AT
        if last is None:
            _LAST_REQUEST_AT = now
            return
        wait_for = min_interval - (now - last)
        if wait_for <= 0:
            _LAST_REQUEST_AT = now
            return
        _LAST_REQUEST_AT = now + wait_for
    if wait_for > 0:
        time.sleep(wait_for)


def _http_get(url: str, headers: Dict[str, str], timeout: float) -> str:
    throttle_pricecharting_request()
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _cents_to_dollars(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        amount = float(val)
        return round(amount / 100.0, 2) if amount > 0 else None
    except (ValueError, TypeError):
        return None


def _payload_from_pricecharting_product(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ungraded = _cents_to_dollars(product.get("loose-price"))
    if not ungraded:
        return None
    sales_volume = product.get("sales-volume")
    try:
        yearly_sales = int(sales_volume) if sales_volume is not None else None
    except (TypeError, ValueError):
        yearly_sales = None
    if yearly_sales is not None and yearly_sales < 0:
        yearly_sales = None
    return {
        "source": "pricecharting_api",
        "has_live_data": True,
        "is_estimate": False,
        "ungraded": ungraded,
        "grade_7": _cents_to_dollars(product.get("cib-price")),
        "grade_8": _cents_to_dollars(product.get("new-price")),
        "grade_9": _cents_to_dollars(product.get("graded-price")),
        "grade_9_5": _cents_to_dollars(product.get("box-only-price")),
        "psa_10": _cents_to_dollars(product.get("manual-only-price")),
        "sales_volume_year": yearly_sales,
        "product_id": product.get("id"),
        "product_url": _product_page_url(product),
    }


def _product_page_url(product: Dict[str, Any]) -> Optional[str]:
    console = str(product.get("console-name") or "").strip()
    name = str(product.get("product-name") or "").strip()
    if not console or not name:
        return None
    return f"https://www.pricecharting.com/game/{_slugify(console)}/{_slugify(name)}"


def _pick_pricecharting_product(
    products: List[Dict[str, Any]],
    card_name: str,
    card_number: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Prefer the product whose title includes this card's number and name."""
    if not products:
        return None
    clean_num = clean_card_number(card_number)
    num_variants = {clean_num} if clean_num else set()
    if clean_num.isdigit():
        num_variants.add(str(int(clean_num)))
        num_variants.add(str(int(clean_num)).zfill(3))
    name_key = re.sub(r"[^a-z0-9]+", "", (card_name or "").lower())

    def _score(product: Dict[str, Any]) -> int:
        pname = str(product.get("product-name") or "")
        pname_compact = re.sub(r"[^a-z0-9#]+", "", pname.lower())
        score = 0
        for variant in num_variants:
            if not variant:
                continue
            if re.search(rf"#{re.escape(variant)}(?:\b|$)", pname, re.I) or pname_compact.endswith(f"#{variant}"):
                score += 10
                break
        pname_key = re.sub(r"[^a-z0-9]+", "", pname.lower())
        if name_key and name_key in pname_key:
            score += 5
        return score

    ranked = sorted(products, key=_score, reverse=True)
    return ranked[0]


def resolve_pricecharting_api_token(db: Session, current_user: Optional[User] = None) -> str:
    """Prefer the current user's token, then env, then any saved user token."""
    if current_user is not None:
        token_setting = (
            db.query(UserSetting)
            .filter(
                UserSetting.user_id == current_user.id,
                UserSetting.key == "pricecharting_api_token",
            )
            .first()
        )
        token = (token_setting.value if token_setting else "") or ""
        if token.strip():
            return token.strip()

    env_token = os.environ.get("PRICECHARTING_API_TOKEN", "").strip()
    if env_token:
        return env_token

    any_token = (
        db.query(UserSetting)
        .filter(
            UserSetting.key == "pricecharting_api_token",
            UserSetting.value.isnot(None),
            UserSetting.value != "",
        )
        .first()
    )
    return ((any_token.value if any_token else "") or "").strip()


def fetch_pricecharting_api(
    api_token: str,
    card_name: str,
    card_number: Optional[str],
    *,
    set_name: Optional[str] = None,
    timeout: float = 5,
    ungraded_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """Query PriceCharting API using paid Legendary API token.

    The products list already includes grade prices, so this uses one request
    per card and stays within the 1 request/second limit.
    """
    if not api_token:
        return None

    clean_num = clean_card_number(card_number)
    query_parts = [card_name, clean_num]
    if set_name:
        query_parts.append(set_name)
    query = " ".join(part for part in query_parts if part).strip()
    search_api_url = (
        f"https://www.pricecharting.com/api/products"
        f"?t={urllib.parse.quote(api_token)}&q={urllib.parse.quote_plus(query)}"
    )

    try:
        raw = _http_get(
            search_api_url,
            headers={"User-Agent": "Pokecollector/1.0"},
            timeout=timeout,
        )
        data = json.loads(raw)
        products = data.get("products", [])
        product = _pick_pricecharting_product(products, card_name, card_number)
        if not product:
            return None
        return _payload_from_pricecharting_product(product)
    except Exception as e:
        logger.warning("PriceCharting API call failed: %s", e)
        return None


def estimate_graded_prices(base_price: Optional[float]) -> Dict[str, Any]:
    """Calculate market grading ratio comparisons based on Ungraded raw baseline."""
    if not is_valid_price(base_price):
        return {
            "source": "market_estimate",
            "has_live_data": False,
            "is_estimate": True,
            "ungraded": None,
            "grade_7": None,
            "grade_8": None,
            "grade_9": None,
            "grade_9_5": None,
            "psa_10": None,
        }

    raw = round(float(base_price), 2)
    return {
        "source": "market_estimate",
        "has_live_data": False,
        "is_estimate": True,
        "ungraded": raw,
        "grade_7": round(raw * 1.05, 2),
        "grade_8": round(raw * 1.35, 2),
        "grade_9": round(raw * 2.80, 2),
        "grade_9_5": round(raw * 3.80, 2),
        "psa_10": round(raw * 8.50, 2),
    }


def get_card_pricecharting_data(
    db: Session,
    current_user: User,
    card: Card,
) -> Dict[str, Any]:
    """Build full PriceCharting graded comparison payload for a card."""
    card_id = card.id
    now = time.time()
    api_token = resolve_pricecharting_api_token(db, current_user)
    cache_key = f"{card_id}:{1 if api_token else 0}"

    if cache_key in _PRICECHARTING_CACHE:
        cached_time, cached_data = _PRICECHARTING_CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    set_name = card.set_ref.name if getattr(card, "set_ref", None) else (card.set_id or "")
    search_url, direct_url = build_pricecharting_urls(card.name, card.number, set_name)

    data: Optional[Dict[str, Any]] = None
    if api_token and not card.is_custom:
        data = fetch_pricecharting_api(api_token, card.name, card.number, set_name=set_name)
        if data and data.get("product_url"):
            direct_url = data["product_url"]

    if not data:
        # Prefer USD TCGPlayer price if available, otherwise Cardmarket market/trend price
        raw_price = (
            card.price_tcg_normal_market
            or card.price_tcg_holo_market
            or card.price_market
            or card.price_trend
        )
        data = estimate_graded_prices(raw_price)

    ungraded_val = data.get("ungraded")

    def _calc_mult(val: Optional[float]) -> Optional[float]:
        if val and ungraded_val and ungraded_val > 0:
            return round(val / ungraded_val, 2)
        return None

    grades = [
        {
            "id": "ungraded",
            "name": "Ungraded",
            "label": "Raw / NM",
            "price": data.get("ungraded"),
            "multiplier": 1.0 if ungraded_val else None,
            "is_psa10": False,
        },
        {
            "id": "grade_7",
            "name": "Grade 7",
            "label": "Near Mint",
            "price": data.get("grade_7"),
            "multiplier": _calc_mult(data.get("grade_7")),
            "is_psa10": False,
        },
        {
            "id": "grade_8",
            "name": "Grade 8",
            "label": "NM-Mint",
            "price": data.get("grade_8"),
            "multiplier": _calc_mult(data.get("grade_8")),
            "is_psa10": False,
        },
        {
            "id": "grade_9",
            "name": "Grade 9",
            "label": "Mint",
            "price": data.get("grade_9"),
            "multiplier": _calc_mult(data.get("grade_9")),
            "is_psa10": False,
        },
        {
            "id": "grade_9_5",
            "name": "Grade 9.5",
            "label": "Gem Mint",
            "price": data.get("grade_9_5"),
            "multiplier": _calc_mult(data.get("grade_9_5")),
            "is_psa10": False,
        },
        {
            "id": "psa_10",
            "name": "PSA 10",
            "label": "Gem Mint / Pristine",
            "price": data.get("psa_10"),
            "multiplier": _calc_mult(data.get("psa_10")),
            "is_psa10": True,
        },
    ]

    result = {
        "card_id": card_id,
        "card_name": card.name,
        "card_number": card.number,
        "set_name": set_name,
        "search_url": search_url,
        "direct_url": direct_url,
        "source": data.get("source", "market_estimate"),
        "has_live_data": data.get("has_live_data", False),
        "is_estimate": data.get("is_estimate", True),
        "currency": "USD",
        "ungraded": data.get("ungraded"),
        "grade_7": data.get("grade_7"),
        "grade_8": data.get("grade_8"),
        "grade_9": data.get("grade_9"),
        "grade_9_5": data.get("grade_9_5"),
        "psa_10": data.get("psa_10"),
        "sales_volume_year": data.get("sales_volume_year"),
        "grades": grades,
    }

    _PRICECHARTING_CACHE[cache_key] = (now, result)
    if result.get("has_live_data"):
        persist_live_ungraded_price(db, card, result.get("ungraded"), commit=True)
    return result


def persist_live_ungraded_price(
    db: Session,
    card: Card,
    ungraded: Optional[float],
    *,
    commit: bool = False,
) -> bool:
    """Store a live PriceCharting ungraded USD price on the card row."""
    if not is_valid_price(ungraded):
        return False
    card.price_pc_ungraded = float(ungraded)
    card.price_pc_synced_at = datetime.datetime.utcnow()
    if commit:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Failed to persist PriceCharting ungraded price for %s", getattr(card, "id", None))
            return False
    return True


def _pricecharting_ungraded_is_fresh(card: Card, now: datetime.datetime) -> bool:
    synced_at = getattr(card, "price_pc_synced_at", None)
    return bool(
        is_valid_price(getattr(card, "price_pc_ungraded", None))
        and synced_at
        and (now - synced_at) < PRICECHARTING_SEARCH_STALE
    )


def enrich_pricecharting_ungraded(
    db: Session,
    current_user: User,
    cards: Iterable[Card],
    *,
    max_fetches: int = 0,
) -> None:
    """Optionally refresh a tiny number of stale ungraded prices.

    Search and dashboard stay cache-only by default (``max_fetches=0``) so they
    cannot burst past PriceCharting's 1 request/second limit. Bulk work belongs
    on the price-sync job.
    """
    if max_fetches <= 0:
        return
    token = resolve_pricecharting_api_token(db, current_user)
    if not token:
        return

    now = datetime.datetime.utcnow()
    to_fetch: List[Card] = []
    for card in cards:
        if getattr(card, "is_custom", False):
            continue
        if _pricecharting_ungraded_is_fresh(card, now):
            continue
        to_fetch.append(card)
        if len(to_fetch) >= max_fetches:
            break

    if not to_fetch:
        return

    updated = False
    for card in to_fetch:
        try:
            data = fetch_pricecharting_api(
                token,
                card.name,
                card.number,
                timeout=8,
                ungraded_only=True,
            )
        except Exception:
            data = None
        if not data or not data.get("has_live_data"):
            continue
        if persist_live_ungraded_price(db, card, data.get("ungraded"), commit=False):
            updated = True

    if updated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Failed to commit PriceCharting ungraded search prices")


def user_ids_with_pricecharting_usd(db: Session) -> set[int]:
    """Users who value the collection with PriceCharting in USD."""
    rows = (
        db.query(UserSetting)
        .filter(UserSetting.key.in_([SEARCH_PRICE_SOURCE_KEY, "currency"]))
        .all()
    )
    by_user: dict[int, dict[str, str]] = {}
    for row in rows:
        by_user.setdefault(row.user_id, {})[row.key] = row.value
    return {
        user_id
        for user_id, settings in by_user.items()
        if normalize_search_price_source(settings.get(SEARCH_PRICE_SOURCE_KEY)) == SEARCH_PRICE_SOURCE_PRICECHARTING
        and str(settings.get("currency") or "EUR").upper() == "USD"
    }


def _tracked_card_ids_for_users(db: Session, user_ids: set[int]) -> set[str]:
    if not user_ids:
        return set()
    collection_ids = {
        card_id
        for (card_id,) in db.query(CollectionItem.card_id).filter(CollectionItem.user_id.in_(user_ids)).all()
        if card_id
    }
    wishlist_ids = {
        card_id
        for (card_id,) in db.query(WishlistItem.card_id).filter(WishlistItem.user_id.in_(user_ids)).all()
        if card_id
    }
    binder_ids = {
        card_id
        for (card_id,) in db.query(BinderCard.card_id)
        .join(Binder, Binder.id == BinderCard.binder_id)
        .filter(Binder.user_id.in_(user_ids))
        .all()
        if card_id
    }
    return collection_ids | wishlist_ids | binder_ids


def sync_pricecharting_ungraded_for_price_sync(db: Session, selected_card_ids: Iterable[str]) -> int:
    """Refresh stale PriceCharting ungraded prices at 1 request/second.

    Runs only when at least one user has Price source = PriceCharting and
    currency = USD, and a token is available from Settings or PRICECHARTING_API_TOKEN.
    """
    user_ids = user_ids_with_pricecharting_usd(db)
    if not user_ids:
        return 0

    token = resolve_pricecharting_api_token(db)
    if not token:
        logger.info(
            "PriceCharting ungraded sync skipped: Price source is PriceCharting with USD, but no API token is set"
        )
        return 0

    wanted_ids = set(selected_card_ids) & _tracked_card_ids_for_users(db, user_ids)
    if not wanted_ids:
        return 0

    cards = (
        db.query(Card)
        .filter(Card.id.in_(wanted_ids), Card.is_custom.is_(False))
        .all()
    )
    now = datetime.datetime.utcnow()
    stale_cards = [card for card in cards if not _pricecharting_ungraded_is_fresh(card, now)]
    if not stale_cards:
        logger.info("PriceCharting ungraded sync: all %s tracked cards are fresh", len(cards))
        return 0

    logger.info(
        "PriceCharting ungraded sync: fetching %s stale cards at 1 request/second",
        len(stale_cards),
    )
    updated = 0
    for index, card in enumerate(stale_cards, start=1):
        try:
            data = fetch_pricecharting_api(
                token,
                card.name,
                card.number,
                timeout=8,
                ungraded_only=True,
            )
        except Exception as exc:
            logger.warning("PriceCharting ungraded sync failed for %s: %s", card.id, exc)
            continue
        if not data or not data.get("has_live_data"):
            continue
        if persist_live_ungraded_price(db, card, data.get("ungraded"), commit=False):
            updated += 1
        if index % 25 == 0:
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.warning("PriceCharting ungraded sync commit failed after %s cards", index)

    if updated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("PriceCharting ungraded sync failed to commit final batch")
            return 0
    logger.info("PriceCharting ungraded sync complete: %s/%s cards updated", updated, len(stale_cards))
    return updated
