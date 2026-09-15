from pydantic_settings import BaseSettings
from functools import lru_cache


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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
