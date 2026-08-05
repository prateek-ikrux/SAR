import asyncio
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


async def main(email: str) -> None:
    client = AsyncIOMotorClient(settings.mongodb_uri)
    collection = client[settings.mongodb_db][settings.allowed_emails_collection]
    await collection.update_one(
        {"email": email.lower()},
        {
            "$setOnInsert": {"added_at": datetime.now(timezone.utc)},
            "$set": {"email": email.lower()},
        },
        upsert=True,
    )
    client.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
