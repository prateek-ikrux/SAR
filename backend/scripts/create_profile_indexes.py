"""Optional: add lookup indexes to ats.profiles.

The email/phone lookup path and the duplicate-expansion endpoint both filter on
`email` and `phone`. Without indexes those are collection scans over ~200k docs.
This adds two non-unique indexes. It writes NO data - indexes only - but it does
touch the existing `ats` database, so it is opt-in and requires --confirm.

    uv run python -m scripts.create_profile_indexes --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pymongo import ASCENDING

from app import db
from app.config import settings


async def run() -> int:
    await db.connect()
    try:
        collection = db.profiles()
        await collection.create_index([("email", ASCENDING)], name="cs_email_lookup")
        await collection.create_index([("phone", ASCENDING)], name="cs_phone_lookup")
        print(f"Indexes ensured on {settings.mongo_db_ats}.{settings.profiles_collection}:")
        for index in await collection.list_indexes().to_list(length=50):
            print(f"  - {index['name']}: {dict(index['key'])}")
        return 0
    finally:
        await db.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create lookup indexes on ats.profiles.")
    parser.add_argument("--confirm", action="store_true", required=True)
    parser.parse_args()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
