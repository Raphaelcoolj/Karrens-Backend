from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlparse
from app.core.config import get_settings

settings = get_settings()

client: AsyncIOMotorClient = None


def _extract_db_name(uri: str) -> str:
    try:
        parsed = urlparse(uri)
        db = parsed.path.lstrip("/")
        if db:
            return db
    except Exception:
        pass
    return "karren"


async def connect_db():
    global client
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_name = _extract_db_name(settings.MONGODB_URL)
    db = client[db_name]
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
    db_name = _extract_db_name(settings.MONGODB_URL)
    return client[db_name]
