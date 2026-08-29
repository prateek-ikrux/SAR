from __future__ import annotations

import logging
import time
from typing import Any

from app import db
from app.security import utcnow

log = logging.getLogger(__name__)

SETTINGS_ID = "search"
CACHE_TTL_SECONDS = 30

# ENN is the mode until an admin explicitly chooses ANN on the Settings page.
# Deliberately a constant rather than a setting: a second way to change this
# would mean ANN could become the default without anyone choosing it.
DEFAULT_SEARCH_EXACT = True

_cache: dict[str, Any] | None = None
_cache_expires_at: float = 0.0


def _defaults() -> dict[str, Any]:
    """The mode a database that has never had one set."""
    return {"search_exact": DEFAULT_SEARCH_EXACT, "updated_at": None, "updated_by": None}


def _shape(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return _defaults()
    return {
        "search_exact": doc.get("search_exact", DEFAULT_SEARCH_EXACT),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


async def get_settings(*, use_cache: bool = True) -> dict[str, Any]:
    """Read the application settings.

    Cached briefly because every search reads this. Without the cache a search
    served from the result pool in ~2ms would still pay an Atlas round trip.
    """
    global _cache, _cache_expires_at

    if use_cache and _cache is not None and time.monotonic() < _cache_expires_at:
        return _cache

    doc = await db.app_settings().find_one({"_id": SETTINGS_ID})
    _cache = _shape(doc)
    _cache_expires_at = time.monotonic() + CACHE_TTL_SECONDS
    return _cache


async def update_settings(*, search_exact: bool, actor_email: str) -> dict[str, Any]:
    global _cache, _cache_expires_at

    now = utcnow()
    await db.app_settings().update_one(
        {"_id": SETTINGS_ID},
        {"$set": {"search_exact": search_exact, "updated_at": now, "updated_by": actor_email}},
        upsert=True,
    )
    # Invalidate immediately so the change is visible on the next search rather
    # than up to CACHE_TTL_SECONDS later.
    _cache = None
    _cache_expires_at = 0.0

    log.info(
        "search settings updated",
        extra={"search_exact": search_exact, "actor": actor_email},
    )
    return await get_settings(use_cache=False)


async def search_uses_exact() -> bool:
    return (await get_settings())["search_exact"]
