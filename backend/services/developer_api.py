import datetime
import secrets
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models import (
    Binder,
    BinderCard,
    Card,
    CollectionItem,
    Set,
    User,
    UserSetting,
)
from services.card_values import effective_market_price, normalize_price_field
from services.card_visibility import visible_any_card_filter
from services.portfolio_valuation import calculate_portfolio_valuation

DEVELOPER_API_KEY_SETTING = "developer_api_key"
DEVELOPER_API_KEY_CREATED_SETTING = "developer_api_key_created_at"


def generate_api_key() -> str:
    """Generate a secure, prefixed API key."""
    return f"pk_live_{secrets.token_hex(24)}"


def get_user_api_key_info(db: Session, user_id: int) -> Dict[str, Any]:
    """Retrieve current API key info for user."""
    key_row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == DEVELOPER_API_KEY_SETTING)
        .first()
    )
    if not key_row or not key_row.value:
        return {"has_key": False, "api_key": None, "created_at": None}

    created_row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == DEVELOPER_API_KEY_CREATED_SETTING)
        .first()
    )
    return {
        "has_key": True,
        "api_key": key_row.value,
        "created_at": created_row.value if created_row else None,
    }


def create_or_regenerate_api_key(db: Session, user_id: int) -> Dict[str, Any]:
    """Create or rotate the developer API key for user."""
    new_key = generate_api_key()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    key_row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == DEVELOPER_API_KEY_SETTING)
        .first()
    )
    if key_row:
        key_row.value = new_key
    else:
        key_row = UserSetting(user_id=user_id, key=DEVELOPER_API_KEY_SETTING, value=new_key)
        db.add(key_row)

    created_row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == DEVELOPER_API_KEY_CREATED_SETTING)
        .first()
    )
    if created_row:
        created_row.value = now_iso
    else:
        created_row = UserSetting(user_id=user_id, key=DEVELOPER_API_KEY_CREATED_SETTING, value=now_iso)
        db.add(created_row)

    db.commit()
    return {"has_key": True, "api_key": new_key, "created_at": now_iso}


def revoke_api_key(db: Session, user_id: int) -> bool:
    """Revoke user's developer API key."""
    db.query(UserSetting).filter(
        UserSetting.user_id == user_id,
        UserSetting.key.in_([DEVELOPER_API_KEY_SETTING, DEVELOPER_API_KEY_CREATED_SETTING]),
    ).delete(synchronize_session=False)
    db.commit()
    return True


def authenticate_api_key(db: Session, raw_key: Any) -> Optional[User]:
    """Authenticate raw API key string against user settings."""
    if not raw_key or not isinstance(raw_key, str):
        return None
    cleaned = raw_key.strip()
    setting = (
        db.query(UserSetting)
        .filter(UserSetting.key == DEVELOPER_API_KEY_SETTING, UserSetting.value == cleaned)
        .first()
    )
    if not setting:
        return None
    user = db.query(User).filter(User.id == setting.user_id, User.is_active == True).first()
    return user


def get_effective_user_currency(db: Session, user_id: int) -> str:
    """Get preferred currency for user."""
    row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == "currency")
        .first()
    )
    return row.value if row and row.value in ("EUR", "USD") else "EUR"


def get_effective_price_field(db: Session, user_id: int, override_field: Optional[str] = None) -> str:
    """Get effective price field for calculation."""
    if override_field:
        return normalize_price_field(override_field)
    row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == "price_primary")
        .first()
    )
    return normalize_price_field(row.value if row and row.value else "trend")


def build_image_links(request: Optional[Request], card: Card) -> Dict[str, Optional[str]]:
    """Build relative and absolute image links for a card."""
    base_url = ""
    if request:
        base_url = str(request.base_url).rstrip("/")
        proto = request.headers.get("x-forwarded-proto")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if proto and host:
            base_url = f"{proto}://{host}"

    local_low = f"/api/images/card/{card.id}/low"
    local_high = f"/api/images/card/{card.id}/high"

    return {
        "small": card.images_small,
        "large": card.images_large,
        "local_small": local_low,
        "local_large": local_high,
        "url_small": f"{base_url}{local_low}" if base_url else local_low,
        "url_large": f"{base_url}{local_high}" if base_url else local_high,
    }


def get_developer_summary(
    db: Session,
    user: User,
    request: Optional[Request] = None,
    top_limit: int = 5,
    price_field_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Summary of user's cards, portfolio value, top cards, and binders.
    Ideal for external dashboards, Home Assistant, and M5 Paper / e-paper displays."""
    price_field = get_effective_price_field(db, user.id, price_field_override)
    currency = get_effective_user_currency(db, user.id)

    # 1. Fetch collection items
    items = (
        db.query(CollectionItem)
        .join(Card, Card.id == CollectionItem.card_id)
        .options(joinedload(CollectionItem.card).joinedload(Card.set_ref))
        .filter(
            CollectionItem.user_id == user.id,
            visible_any_card_filter(db, user.id, "all"),
        )
        .all()
    )

    total_cards = sum(item.quantity for item in items)
    unique_cards = len(items)

    valuation = calculate_portfolio_valuation(
        db,
        user.id,
        price_field,
        collection_items=items,
    )
    total_value = round(valuation.total_value, 2)
    total_cost = round(valuation.active_cost_basis, 2)
    pnl = round(valuation.total_pnl, 2)
    pnl_percentage = round((pnl / total_cost * 100), 2) if total_cost > 0 else 0.0

    # Sets count
    owned_set_ids = {item.card.set_id for item in items if item.card and item.card.set_id}

    # Top cards calculation
    def _item_val(item: CollectionItem) -> float:
        if not item.card:
            return 0.0
        unit = effective_market_price(item.card, item.variant, price_field)
        return unit * item.quantity

    sorted_items = sorted([item for item in items if item.card], key=_item_val, reverse=True)
    top_items = sorted_items[:top_limit]

    top_cards_payload = []
    for item in top_items:
        card = item.card
        unit_price = round(effective_market_price(card, item.variant, price_field), 2)
        item_total = round(unit_price * item.quantity, 2)
        set_name = card.set_ref.name if getattr(card, "set_ref", None) else (card.set_id or "")

        top_cards_payload.append({
            "card_id": card.id,
            "collection_item_id": item.id,
            "name": card.name,
            "set_id": card.set_id,
            "set_name": set_name,
            "number": card.number,
            "rarity": card.rarity,
            "variant": item.variant,
            "condition": item.condition,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "total_value": item_total,
            "images": build_image_links(request, card),
        })

    # Binders summary
    binders = db.query(Binder).filter(Binder.user_id == user.id).all()
    binders_payload = []
    for b in binders:
        cards_query = (
            db.query(BinderCard)
            .join(Card, Card.id == BinderCard.card_id)
            .options(joinedload(BinderCard.card), joinedload(BinderCard.collection_item))
            .filter(
                BinderCard.binder_id == b.id,
                visible_any_card_filter(db, user.id, "all"),
            )
            .all()
        )
        b_total_cards = sum(bc.required_quantity for bc in cards_query)
        b_unique_cards = len({bc.card_id for bc in cards_query})
        b_total_val = sum(
            round(
                effective_market_price(
                    bc.card,
                    bc.collection_item.variant if bc.collection_item else "Normal",
                    price_field,
                )
                * bc.required_quantity,
                2,
            )
            for bc in cards_query
            if bc.card
        )
        binders_payload.append({
            "id": b.id,
            "name": b.name,
            "color": b.color,
            "binder_type": b.binder_type or "collection",
            "format": b.format,
            "card_count": b_total_cards,
            "unique_card_count": b_unique_cards,
            "total_value": round(b_total_val, 2),
        })

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "avatar_id": user.avatar_id,
        },
        "currency": currency,
        "price_basis": price_field,
        "stats": {
            "total_cards": total_cards,
            "unique_cards": unique_cards,
            "total_value": total_value,
            "total_cost": total_cost,
            "pnl": pnl,
            "pnl_percentage": pnl_percentage,
            "total_sets": len(owned_set_ids),
            "total_binders": len(binders),
        },
        "top_cards": top_cards_payload,
        "binders": binders_payload,
    }


def get_developer_cards(
    db: Session,
    user: User,
    request: Optional[Request] = None,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    set_id: Optional[str] = None,
    sort: str = "value",
    order: str = "desc",
    price_field_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch paginated card entries from user's collection."""
    price_field = get_effective_price_field(db, user.id, price_field_override)

    query = (
        db.query(CollectionItem)
        .join(Card, Card.id == CollectionItem.card_id)
        .options(joinedload(CollectionItem.card).joinedload(Card.set_ref))
        .filter(
            CollectionItem.user_id == user.id,
            visible_any_card_filter(db, user.id, "all"),
        )
    )

    if set_id:
        query = query.filter(Card.set_id == set_id)

    if search:
        search_term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Card.name).like(search_term),
                func.lower(Card.number).like(search_term),
            )
        )

    all_items = query.all()
    total_matches = len(all_items)

    def _sort_key(item: CollectionItem):
        card = item.card
        if not card:
            return 0
        if sort == "value":
            return effective_market_price(card, item.variant, price_field) * item.quantity
        if sort == "name":
            return (card.name or "").lower()
        if sort == "number":
            return str(card.number or "")
        if sort == "quantity":
            return item.quantity or 0
        if sort == "date":
            return item.added_at or datetime.datetime.min
        return 0

    reverse = (order.lower() == "desc")
    sorted_items = sorted(all_items, key=_sort_key, reverse=reverse)
    paged_items = sorted_items[offset : offset + limit]

    cards_payload = []
    for item in paged_items:
        card = item.card
        unit_price = round(effective_market_price(card, item.variant, price_field), 2)
        item_total = round(unit_price * item.quantity, 2)
        set_name = card.set_ref.name if getattr(card, "set_ref", None) else (card.set_id or "")

        cards_payload.append({
            "collection_item_id": item.id,
            "card_id": card.id,
            "name": card.name,
            "set_id": card.set_id,
            "set_name": set_name,
            "number": card.number,
            "rarity": card.rarity,
            "variant": item.variant,
            "condition": item.condition,
            "lang": item.lang,
            "quantity": item.quantity,
            "purchase_price": item.purchase_price,
            "unit_price": unit_price,
            "total_value": item_total,
            "added_at": item.added_at.isoformat() if item.added_at else None,
            "images": build_image_links(request, card),
        })

    return {
        "total": total_matches,
        "limit": limit,
        "offset": offset,
        "cards": cards_payload,
    }


def get_developer_binders(
    db: Session,
    user: User,
    request: Optional[Request] = None,
    price_field_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch user's binders with card counts and values."""
    price_field = get_effective_price_field(db, user.id, price_field_override)
    binders = db.query(Binder).filter(Binder.user_id == user.id).all()

    binders_payload = []
    for b in binders:
        cards_query = (
            db.query(BinderCard)
            .join(Card, Card.id == BinderCard.card_id)
            .options(joinedload(BinderCard.card), joinedload(BinderCard.collection_item))
            .filter(
                BinderCard.binder_id == b.id,
                visible_any_card_filter(db, user.id, "all"),
            )
            .all()
        )
        b_total_cards = sum(bc.required_quantity for bc in cards_query)
        b_unique_cards = len({bc.card_id for bc in cards_query})
        b_total_val = sum(
            round(
                effective_market_price(
                    bc.card,
                    bc.collection_item.variant if bc.collection_item else "Normal",
                    price_field,
                )
                * bc.required_quantity,
                2,
            )
            for bc in cards_query
            if bc.card
        )
        binders_payload.append({
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "color": b.color,
            "binder_type": b.binder_type or "collection",
            "format": b.format,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "card_count": b_total_cards,
            "unique_card_count": b_unique_cards,
            "total_value": round(b_total_val, 2),
        })

    return {
        "total": len(binders_payload),
        "binders": binders_payload,
    }


def get_developer_binder_detail(
    db: Session,
    user: User,
    binder_id: int,
    request: Optional[Request] = None,
    price_field_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch details and cards inside a specific binder."""
    binder = db.query(Binder).filter(Binder.id == binder_id, Binder.user_id == user.id).first()
    if not binder:
        raise HTTPException(status_code=404, detail="Binder not found")

    price_field = get_effective_price_field(db, user.id, price_field_override)

    cards_query = (
        db.query(BinderCard)
        .join(Card, Card.id == BinderCard.card_id)
        .options(
            joinedload(BinderCard.card).joinedload(Card.set_ref),
            joinedload(BinderCard.collection_item),
        )
        .filter(
            BinderCard.binder_id == binder.id,
            visible_any_card_filter(db, user.id, "all"),
        )
        .all()
    )

    cards_payload = []
    total_val = 0.0
    for bc in cards_query:
        card = bc.card
        if not card:
            continue
        variant = bc.collection_item.variant if bc.collection_item else "Normal"
        condition = bc.collection_item.condition if bc.collection_item else "NM"
        unit_price = round(effective_market_price(card, variant, price_field), 2)
        card_total = round(unit_price * bc.required_quantity, 2)
        total_val += card_total
        set_name = card.set_ref.name if getattr(card, "set_ref", None) else (card.set_id or "")

        cards_payload.append({
            "binder_card_id": bc.id,
            "card_id": card.id,
            "collection_item_id": bc.collection_item_id,
            "name": card.name,
            "set_id": card.set_id,
            "set_name": set_name,
            "number": card.number,
            "rarity": card.rarity,
            "variant": variant,
            "condition": condition,
            "quantity": bc.required_quantity,
            "unit_price": unit_price,
            "total_value": card_total,
            "images": build_image_links(request, card),
        })

    return {
        "binder": {
            "id": binder.id,
            "name": binder.name,
            "description": binder.description,
            "color": binder.color,
            "binder_type": binder.binder_type or "collection",
            "format": binder.format,
            "created_at": binder.created_at.isoformat() if binder.created_at else None,
            "card_count": sum(bc.required_quantity for bc in cards_query),
            "unique_card_count": len(cards_payload),
            "total_value": round(total_val, 2),
        },
        "cards": cards_payload,
    }
