"""Service for retrieving PriceCharting card pricing and graded price comparisons."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from models import Card, User, UserSetting
from services.price_utils import is_valid_price

logger = logging.getLogger(__name__)

# Cache in-memory: card_id -> (timestamp, data_dict)
_PRICECHARTING_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


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


def fetch_pricecharting_api(
    api_token: str,
    card_name: str,
    card_number: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Query PriceCharting API using paid Legendary API token."""
    if not api_token:
        return None

    clean_num = clean_card_number(card_number)
    query = f"{card_name} {clean_num}".strip()
    search_api_url = (
        f"https://www.pricecharting.com/api/products"
        f"?t={urllib.parse.quote(api_token)}&q={urllib.parse.quote_plus(query)}"
    )

    try:
        req = urllib.request.Request(
            search_api_url,
            headers={"User-Agent": "Pokecollector/1.0"},
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            products = data.get("products", [])
            if not products:
                return None
            product_id = products[0].get("id")
            if not product_id:
                return None

        detail_api_url = (
            f"https://www.pricecharting.com/api/product"
            f"?t={urllib.parse.quote(api_token)}&id={product_id}"
        )
        req2 = urllib.request.Request(
            detail_api_url,
            headers={"User-Agent": "Pokecollector/1.0"},
        )
        with urllib.request.urlopen(req2, context=ctx, timeout=5) as resp2:
            detail = json.loads(resp2.read().decode("utf-8"))

            def _to_dollars(val: Any) -> Optional[float]:
                if val is None:
                    return None
                try:
                    f = float(val)
                    return round(f / 100.0, 2) if f > 0 else None
                except (ValueError, TypeError):
                    return None

            return {
                "source": "pricecharting_api",
                "has_live_data": True,
                "is_estimate": False,
                "ungraded": _to_dollars(detail.get("loose-price")),
                "grade_7": _to_dollars(detail.get("cib-price")),
                "grade_8": _to_dollars(detail.get("new-price")),
                "grade_9": _to_dollars(detail.get("graded-price")),
                "grade_9_5": _to_dollars(detail.get("box-only-price")),
                "psa_10": _to_dollars(detail.get("manual-only-price")),
            }
    except Exception as e:
        logger.warning("PriceCharting API call failed: %s", e)
        return None


def fetch_pricecharting_web(direct_url: str) -> Optional[Dict[str, Any]]:
    """Attempt web fetch of PriceCharting page if accessible."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    ctx = ssl.create_default_context()
    req = urllib.request.Request(direct_url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
            if resp.status != 200:
                return None
            html = resp.read().decode("utf-8", errors="ignore")

            price_keys = {
                "used_price": "ungraded",
                "complete_price": "grade_7",
                "new_price": "grade_8",
                "graded_price": "grade_9",
                "box_only_price": "grade_9_5",
                "manual_only_price": "psa_10",
            }
            results: dict[str, Optional[float]] = {}
            for pid, name in price_keys.items():
                m = re.search(
                    r'id="' + pid + r'"[^>]*>.*?<span class="price js-price">([^<]+)</span>',
                    html,
                    re.DOTALL,
                )
                if m:
                    text = m.group(1).strip().replace("$", "").replace(",", "")
                    try:
                        val = float(text)
                        if val > 0:
                            results[name] = round(val, 2)
                    except ValueError:
                        pass

            if results.get("ungraded") or results.get("psa_10") or results.get("grade_9"):
                return {
                    "source": "pricecharting_web",
                    "has_live_data": True,
                    "is_estimate": False,
                    "ungraded": results.get("ungraded"),
                    "grade_7": results.get("grade_7"),
                    "grade_8": results.get("grade_8"),
                    "grade_9": results.get("grade_9"),
                    "grade_9_5": results.get("grade_9_5"),
                    "psa_10": results.get("psa_10"),
                }
    except Exception as e:
        logger.debug("PriceCharting web fetch failed (%s): %s", direct_url, e)
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

    # Check cache
    if card_id in _PRICECHARTING_CACHE:
        cached_time, cached_data = _PRICECHARTING_CACHE[card_id]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    set_name = card.set_ref.name if getattr(card, "set_ref", None) else (card.set_id or "")
    search_url, direct_url = build_pricecharting_urls(card.name, card.number, set_name)

    # 1. Try API token if user has one configured
    token_setting = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == current_user.id, UserSetting.key == "pricecharting_api_token")
        .first()
    )
    api_token = (token_setting.value if token_setting else os.environ.get("PRICECHARTING_API_TOKEN", "")).strip()

    data: Optional[Dict[str, Any]] = None
    if api_token:
        data = fetch_pricecharting_api(api_token, card.name, card.number)

    # 2. Try web fetch if no token
    if not data and not card.is_custom:
        data = fetch_pricecharting_web(direct_url)

    # 3. Fallback to market estimate from card's own raw price
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
        "grades": grades,
    }

    _PRICECHARTING_CACHE[card_id] = (now, result)
    return result
