"""Persistent local cache for proxied card, set, and product images."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

_CARD_SIZE_RE = re.compile(r":(small|large)(?::|$)")

CACHE_ROOT = Path(os.environ.get("CARD_IMAGE_CACHE_DIR", "/app/data/card-images"))
_DEFAULT_CONTENT_TYPE = "image/webp"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _card_dir(card_id: str) -> Path:
    digest = _digest(card_id)
    return CACHE_ROOT / "card" / digest[:2] / digest


def files_for_key(key: str) -> tuple[Path, Path]:
    """Return (data_path, content_type_path) for an image_cache key."""
    if key.startswith("card:"):
        body = key[len("card:"):]
        match = _CARD_SIZE_RE.search(body)
        if match:
            card_id = body[:match.start()]
            rest = body[match.start() + 1:] or "image"
            rest_digest = _digest(rest)
            folder = _card_dir(card_id)
            return folder / rest_digest, folder / f"{rest_digest}.type"

    if key.startswith("set:"):
        parts = key.split(":")
        set_id = parts[1] if len(parts) > 1 else ""
        rest = "-".join(parts[2:]) or "image"
        digest = _digest(set_id)
        rest_digest = _digest(rest)
        folder = CACHE_ROOT / "set" / digest[:2] / digest
        return folder / rest_digest, folder / f"{rest_digest}.type"

    if key.startswith("product:"):
        product_digest = key.rsplit(":", 1)[-1]
        folder = CACHE_ROOT / "product" / product_digest[:2]
        return folder / product_digest, folder / f"{product_digest}.type"

    digest = _digest(key)
    folder = CACHE_ROOT / "other" / digest[:2]
    return folder / digest, folder / f"{digest}.type"


def lookup(key: str) -> tuple[Path, str] | None:
    data_path, type_path = files_for_key(key)
    if not data_path.is_file():
        return None
    content_type = _DEFAULT_CONTENT_TYPE
    if type_path.is_file():
        content_type = type_path.read_text(encoding="utf-8").strip() or content_type
    return data_path, content_type


def write(key: str, data: bytes, content_type: str) -> Path:
    data_path, type_path = files_for_key(key)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=data_path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, data_path)
        type_path.write_text(
            (content_type or _DEFAULT_CONTENT_TYPE).split(";", 1)[0].strip() or _DEFAULT_CONTENT_TYPE,
            encoding="utf-8",
        )
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return data_path


def delete_keys(keys: Iterable[str]) -> None:
    for key in keys:
        data_path, type_path = files_for_key(key)
        data_path.unlink(missing_ok=True)
        type_path.unlink(missing_ok=True)


def delete_card_images(card_id: str) -> None:
    folder = _card_dir(card_id)
    if folder.exists():
        shutil.rmtree(folder)
    parent = folder.parent
    if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def clear_cache() -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    for child in CACHE_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def purge_card_images(db, card_id: str) -> None:
    from models import ImageCache

    db.query(ImageCache).filter(
        ImageCache.image_key.like(f"card:{card_id}:%")
    ).delete(synchronize_session=False)
    delete_card_images(card_id)


def purge_keys(db, keys: Iterable[str]) -> None:
    key_list = [key for key in keys if key]
    if not key_list:
        return
    from models import ImageCache

    db.query(ImageCache).filter(ImageCache.image_key.in_(key_list)).delete(synchronize_session=False)
    delete_keys(key_list)
