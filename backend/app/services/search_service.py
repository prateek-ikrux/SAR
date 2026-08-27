from __future__ import annotations

import logging
import re
import time
from typing import Any

from app import db
from app.config import settings
from app.services import dedupe
from app.services.cache import make_key, search_pool_cache

log = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_WHITESPACE_RE = re.compile(r"\s+")
_MD_NOISE_RE = re.compile(r"[#*_`>]+")

SNIPPET_PREVIEW_CHARS = 320


# --------------------------------------------------------------------- presentation
def extract_headline(text: str) -> str | None:
    """Best-effort candidate name from the resume's first markdown heading.

    No LLM, no enrichment pipeline - just the first '## NAME' line, which is how
    the converted resumes in this corpus are shaped. Falls back to the first
    non-trivial line.
    """
    if not text:
        return None
    for line in text.splitlines()[:40]:
        match = _HEADING_RE.match(line)
        if match:
            candidate = match.group(1).strip()
            if 2 <= len(candidate) <= 120:
                return candidate.title() if candidate.isupper() else candidate
    for line in text.splitlines()[:10]:
        stripped = _MD_NOISE_RE.sub("", line).strip()
        if 2 <= len(stripped) <= 120:
            return stripped.title() if stripped.isupper() else stripped
    return None


def build_snippet(text: str, limit: int = SNIPPET_PREVIEW_CHARS) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", _MD_NOISE_RE.sub(" ", text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "…"


def _shape(doc: dict[str, Any]) -> dict[str, Any]:
    raw = doc.get("snippet") or ""
    return {
        "id": str(doc["_id"]),
        "headline": extract_headline(raw),
        "email": doc.get("email"),
        "phone": doc.get("phone"),
        "file_name": doc.get("file_name"),
        "score": float(doc.get("score", 0.0)),
        "snippet": build_snippet(raw),
        "collapsed": False,
        "duplicate_count": 1,
        "duplicates": [],
    }


_PROJECTION: dict[str, Any] = {
    "_id": 1,
    "email": 1,
    "phone": 1,
    "file_name": 1,
    "snippet": {"$substrCP": [{"$ifNull": ["$document", ""]}, 0, settings.search_snippet_chars]},
}


# --------------------------------------------------------------------- retrieval
async def _run_vector_search(*, query: str, pool_size: int, exact: bool) -> list[dict[str, Any]]:
    vector_stage: dict[str, Any] = {
        "index": settings.vector_index_name,
        "path": settings.vector_path,
        # Atlas automated embedding: pass raw text, Atlas embeds it with the
        # model declared on the index (voyage-4). No queryVector needed.
        "query": {"text": query},
        "limit": pool_size,
    }
    if exact:
        vector_stage["exact"] = True
    else:
        vector_stage["numCandidates"] = min(pool_size * settings.search_ann_num_candidates_multiplier, 10_000)

    pipeline: list[dict[str, Any]] = [
        {"$vectorSearch": vector_stage},
        {"$project": {**_PROJECTION, "score": {"$meta": "vectorSearchScore"}}},
    ]

    started = time.perf_counter()
    cursor = await db.profiles().aggregate(pipeline)
    docs = await cursor.to_list(length=pool_size)
    log.info(
        "vector search executed",
        extra={
            "mode": "enn" if exact else "ann",
            "pool_size": pool_size,
            "returned": len(docs),
            "db_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return [_shape(doc) for doc in docs]


async def _identifier_lookup(query: str) -> list[dict[str, Any]]:
    """Exact lookup for an email address or phone number.

    Semantic similarity is the wrong tool for an identifier - a recruiter typing
    a phone number wants that person, not people whose numbers look alike.
    """
    stripped = query.strip()
    if dedupe.looks_like_email(stripped):
        mongo_filter = {"email": {"$regex": f"^{re.escape(stripped.lower())}$", "$options": "i"}}
    else:
        phone = dedupe.normalize_phone(stripped)
        if not phone:
            return []
        mongo_filter = {"phone": {"$regex": f"{re.escape(phone)}$"}}

    cursor = await db.profiles().aggregate(
        [{"$match": mongo_filter}, {"$limit": 50}, {"$project": {**_PROJECTION, "score": {"$literal": 1.0}}}]
    )
    docs = await cursor.to_list(length=50)
    return [_shape(doc) for doc in docs]


# --------------------------------------------------------------------- public API
async def search(
    *,
    query: str,
    page: int,
    page_size: int,
    exact: bool | None,
    collapse_duplicates: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    query = query.strip()
    use_exact = settings.search_default_exact if exact is None else exact

    # 1. An email or phone number is an identifier, not a description.
    if dedupe.looks_like_email(query) or dedupe.looks_like_phone(query):
        hits = await _identifier_lookup(query)
        results = dedupe.collapse(hits) if collapse_duplicates else hits
        start = (page - 1) * page_size
        window = results[start : start + page_size]
        return {
            "query": query,
            "strategy": "identifier",
            "mode": None,
            "page": page,
            "page_size": page_size,
            "results": window,
            "returned": len(window),
            "pool_size": len(hits),
            "total_in_pool": len(results),
            "has_more": len(results) > start + page_size,
            "pool_exhausted": True,
            "took_ms": round((time.perf_counter() - started) * 1000),
            "cached": False,
        }

    # 2. Vector search over a pool, paginated in memory.
    #
    # $vectorSearch has no skip/offset, so deep pages can only be served by
    # asking for a larger `limit` and slicing. Re-running the query for every
    # page would repeat the whole scan (expensive under ENN, which is
    # exhaustive), so one pool is fetched and cached, then paged locally.
    needed = page * page_size
    overfetch = 3 if collapse_duplicates else 1
    pool_size = min(max(settings.search_pool_size, needed * overfetch), settings.search_max_pool_size)

    cache_key = make_key(
        q=query,
        exact=use_exact,
        index=settings.vector_index_name,
        path=settings.vector_path,
        pool=pool_size,
    )
    cached_entry = search_pool_cache.get(cache_key)
    was_cached = cached_entry is not None

    if cached_entry is None:
        hits = await _run_vector_search(query=query, pool_size=pool_size, exact=use_exact)
        search_pool_cache.set(cache_key, hits)
    else:
        hits = cached_entry

    results = dedupe.collapse(hits) if collapse_duplicates else hits
    pool_exhausted = len(hits) < pool_size

    start = (page - 1) * page_size
    window = results[start : start + page_size]
    has_more = len(results) > start + page_size or (
        not pool_exhausted and pool_size < settings.search_max_pool_size
    )

    return {
        "query": query,
        "strategy": "vector",
        "mode": "enn" if use_exact else "ann",
        "page": page,
        "page_size": page_size,
        "results": window,
        "returned": len(window),
        "pool_size": pool_size,
        "total_in_pool": len(results),
        "has_more": has_more,
        "pool_exhausted": pool_exhausted,
        "took_ms": round((time.perf_counter() - started) * 1000),
        "cached": was_cached,
    }


async def get_profile(profile_id: str) -> dict[str, Any] | None:
    from app.services.auth_service import to_object_id

    doc = await db.profiles().find_one({"_id": to_object_id(profile_id)})
    if not doc:
        return None

    duplicates: list[dict[str, Any]] = []
    dup_filter = dedupe.duplicate_query(doc.get("email"), doc.get("phone"))
    if dup_filter:
        cursor = (
            await db.profiles()
            .find({"$and": [dup_filter, {"_id": {"$ne": doc["_id"]}}]}, {"file_name": 1})
            .to_list(length=25)
        )
        duplicates = [{"id": str(d["_id"]), "file_name": d.get("file_name"), "score": None} for d in cursor]

    document = doc.get("document", "") or ""
    return {
        "id": str(doc["_id"]),
        "headline": extract_headline(document),
        "email": doc.get("email"),
        "phone": doc.get("phone"),
        "file_name": doc.get("file_name"),
        "document": document,
        "duplicate_count": 1 + len(duplicates),
        "duplicates": duplicates,
    }
