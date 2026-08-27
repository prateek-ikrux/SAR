"""Verify the Atlas side of the setup before trusting the API.

    uv run python -m scripts.check_setup --query "java developer with 9 plus years of experience"

Reports the profile count, the vector index definition, and then runs the same
query against every embedded path in both ENN and ANN mode with timings, so you
can see for yourself which path actually returns sensible candidates and what
exhaustive search costs at your corpus size.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from app import db
from app.config import settings
from app.services.search_service import extract_headline


async def list_search_indexes() -> list[dict]:
    try:
        cursor = await db.profiles().aggregate([{"$listSearchIndexes": {}}])
        return await cursor.to_list(length=20)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! could not list search indexes: {exc}")
        return []


async def probe(path: str, query: str, exact: bool, limit: int) -> None:
    stage = {
        "index": settings.vector_index_name,
        "path": path,
        "query": {"text": query},
        "limit": limit,
    }
    if exact:
        stage["exact"] = True
    else:
        stage["numCandidates"] = limit * 15

    mode = "ENN" if exact else "ANN"
    started = time.perf_counter()
    try:
        cursor = await db.profiles().aggregate(
            [
                {"$vectorSearch": stage},
                {
                    "$project": {
                        "email": 1,
                        "file_name": 1,
                        "head": {"$substrCP": [{"$ifNull": ["$document", ""]}, 0, 400]},
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]
        )
        docs = await cursor.to_list(length=limit)
    except Exception as exc:  # noqa: BLE001
        print(f"  path={path:<12} {mode}: FAILED - {exc}")
        return

    elapsed = round((time.perf_counter() - started) * 1000)
    print(f"  path={path:<12} {mode}: {len(docs)} hits in {elapsed} ms")
    for doc in docs[:3]:
        name = extract_headline(doc.get("head", "")) or "?"
        print(f"      {doc['score']:.4f}  {name[:38]:<38} {doc.get('email') or '-'}")


async def run(query: str, limit: int, paths: list[str]) -> int:
    await db.connect()
    try:
        print(f"\ncluster       : {settings.mongodb_uri.split('@')[-1].split('/')[0]}")
        print(f"source db     : {settings.mongo_db_ats}.{settings.profiles_collection}")
        print(f"app db        : {settings.mongo_db_app}")

        count = await db.profiles().estimated_document_count()
        print(f"profiles      : ~{count:,}")

        print("\nsearch indexes:")
        for index in await list_search_indexes():
            status = index.get("status", "?")
            queryable = index.get("queryable", False)
            print(
                f"  - {index.get('name')}  type={index.get('type')}  status={status}  queryable={queryable}"
            )
            for field in (index.get("latestDefinition") or {}).get("fields", []):
                kind = str(field.get("type"))
                path = str(field.get("path"))
                model = field.get("model", "-")
                print(f"      {kind:<10} path={path:<12} model={model}")

        print(f"\nquery: {query!r}")
        for path in paths:
            await probe(path, query, exact=True, limit=limit)
            await probe(path, query, exact=False, limit=limit)
        print()
        return 0
    finally:
        await db.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the Atlas vector search setup.")
    parser.add_argument("--query", default="java developer with 9 plus years of experience")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--paths",
        default="document,file_name",
        help="Comma separated embedded paths to compare (default: document,file_name)",
    )
    args = parser.parse_args()
    paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    return asyncio.run(run(args.query, args.limit, paths))


if __name__ == "__main__":
    sys.exit(main())
