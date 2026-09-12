"""Shared card upsert helper."""

from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from models import Card, Set
from services.image_disk_cache import purge_keys
from services.price_utils import preserve_existing_prices_for_invalid_update


def _apply_set_digital_flag(db: Session, card_data: dict) -> None:
    if card_data.get("is_digital") or not card_data.get("set_id"):
        return
    set_lang = card_data.get("lang") or "en"
    set_row = db.query(Set.is_digital).filter(
        Set.tcg_set_id == card_data["set_id"],
        Set.lang == set_lang,
    ).first()
    if set_row and set_row[0]:
        card_data["is_digital"] = True


def upsert_card(db: Session, card_data: dict) -> Card:
    """Insert or update a card row consistently across sync and API flows."""
    existing = db.query(Card).filter(Card.id == card_data["id"]).first()
    card_data["updated_at"] = datetime.datetime.utcnow()
    _apply_set_digital_flag(db, card_data)
    preserve_existing_prices_for_invalid_update(card_data, existing)
    has_api_image = bool(card_data.get("images_small") or card_data.get("images_large"))
    if existing:
        for key, value in card_data.items():
            if key != "id":
                setattr(existing, key, value)
        if has_api_image:
            existing.custom_image_url = None
            purge_keys(db, [
                f"card:{existing.id}:small:custom",
                f"card:{existing.id}:large:custom",
            ])
    else:
        existing = Card(**card_data)
        db.add(existing)
    return existing
