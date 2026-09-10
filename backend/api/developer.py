from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.developer_api import (
    authenticate_api_key,
    get_developer_summary,
    get_developer_cards,
    get_developer_binders,
    get_developer_binder_detail,
)

router = APIRouter()
security_bearer = HTTPBearer(auto_error=False)


def get_developer_user(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key_query: Optional[str] = Query(None, alias="api_key"),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> User:
    """Authenticate developer API request via header, query parameter, or Bearer token."""
    key = None
    if isinstance(x_api_key, str) and x_api_key:
        key = x_api_key
    elif isinstance(api_key_query, str) and api_key_query:
        key = api_key_query
    elif bearer_creds and hasattr(bearer_creds, "credentials") and isinstance(bearer_creds.credentials, str):
        key = bearer_creds.credentials

    if not key and request and hasattr(request, "headers"):
        auth_hdr = request.headers.get("Authorization", "")
        if auth_hdr.startswith("ApiKey "):
            key = auth_hdr[7:].strip()
        elif auth_hdr.startswith("Bearer "):
            key = auth_hdr[7:].strip()

    if not key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide via 'X-API-Key' header, '?api_key=' query parameter, or 'Authorization: Bearer <key>'.",
        )

    user = authenticate_api_key(db, key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


@router.get("/ping")
def ping(user: User = Depends(get_developer_user)):
    """Simple health / credential test endpoint."""
    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "avatar_id": user.avatar_id,
        },
    }


@router.get("/summary")
def get_summary(
    request: Request,
    top_limit: int = Query(default=5, ge=1, le=50, description="Number of top cards to return"),
    price_field: Optional[str] = Query(default=None, description="Price field override (trend, market, avg, avg1, avg7, avg30, low)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_developer_user),
):
    """Get high-level summary designed for M5 Paper / e-paper devices and dashboards."""
    return get_developer_summary(
        db=db,
        user=user,
        request=request,
        top_limit=top_limit,
        price_field_override=price_field,
    )


@router.get("/cards")
def get_cards(
    request: Request,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None, description="Search term for card name or number"),
    set_id: Optional[str] = Query(default=None, description="Filter cards by set ID"),
    sort: str = Query(default="value", description="Sort field: value, name, date, quantity, number"),
    order: str = Query(default="desc", description="Sort direction: asc or desc"),
    price_field: Optional[str] = Query(default=None, description="Price field override"),
    db: Session = Depends(get_db),
    user: User = Depends(get_developer_user),
):
    """Get user's cards with pagination, sorting, and image links."""
    return get_developer_cards(
        db=db,
        user=user,
        request=request,
        limit=limit,
        offset=offset,
        search=search,
        set_id=set_id,
        sort=sort,
        order=order,
        price_field_override=price_field,
    )


@router.get("/binders")
def get_binders(
    request: Request,
    price_field: Optional[str] = Query(default=None, description="Price field override"),
    db: Session = Depends(get_db),
    user: User = Depends(get_developer_user),
):
    """Get list of user's binders with card counts and computed values."""
    return get_developer_binders(
        db=db,
        user=user,
        request=request,
        price_field_override=price_field,
    )


@router.get("/binders/{binder_id}")
def get_binder(
    binder_id: int,
    request: Request,
    price_field: Optional[str] = Query(default=None, description="Price field override"),
    db: Session = Depends(get_db),
    user: User = Depends(get_developer_user),
):
    """Get binder details and cards with image links and valuations."""
    return get_developer_binder_detail(
        db=db,
        user=user,
        binder_id=binder_id,
        request=request,
        price_field_override=price_field,
    )
