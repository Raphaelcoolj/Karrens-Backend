from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017/karren"
    MONGODB_DB_NAME: str = ""

    TWELVE_DATA_API_KEY: str = ""

    GROQ_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    AI_PRIMARY_PROVIDER: str = "groq"
    AI_FALLBACK_PROVIDER: str = "mistral"
    AI_TIMEOUT: int = 30

    CORS_ORIGINS: list[str] = ["*"]

    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:noreply@karren.app"

    # --- Signal thresholds (optional overrides) ---------------------------
    # When unset (None) the defaults from app.core.thresholds.SignalThresholds
    # are used.  Set these via environment to tune the signal engine without
    # touching code.
    CONFIDENCE_TIER_VERY_HIGH: Optional[int] = None
    CONFIDENCE_TIER_HIGH: Optional[int] = None
    CONFIDENCE_TIER_MODERATE: Optional[int] = None
    CONFIDENCE_TIER_LOW: Optional[int] = None
    CONFIDENCE_REFERENCE_EVIDENCE: Optional[float] = None

    # Push-notification policy
    NOTIFY_MIN_CONFIDENCE: Optional[int] = None
    NOTIFY_MIN_CONFIDENCE_DELTA: Optional[int] = None
    NOTIFY_ON_HIGH_CONFIDENCE: Optional[bool] = None
    NOTIFY_ON_VALIDATED_SETUP: Optional[bool] = None
    NOTIFY_ON_CONFIDENCE_INCREASE: Optional[bool] = None
    NOTIFY_ON_DIRECTION_CHANGE: Optional[bool] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
