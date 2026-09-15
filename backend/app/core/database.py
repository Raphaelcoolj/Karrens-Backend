from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

settings = get_settings()

client: AsyncIOMotorClient = None


async def connect_db():
    global client
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    await db.analyses.create_index("timestamp")
    await db.analyses.create_index("pair")
    await db.signals.create_index("timestamp")
    await db.strategies.create_index("created_at")
    return db


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return client[settings.MONGODB_DB_NAME]
