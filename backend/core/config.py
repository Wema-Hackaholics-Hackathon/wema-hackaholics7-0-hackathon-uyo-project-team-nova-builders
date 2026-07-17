from functools import lru_cache
from typing import List

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=True, extra="ignore"
    )

    API_PREFIX: str
    DEBUG: bool = Field(default=False)
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173,https://foid-mu.vercel.app"
    )
    PORT: int = Field(default=8080)
    PROD_DB: str = Field(...)
    DEV_DB: str = Field(...)
    SECRET_KEY: str = Field(...)

    

    @field_validator("ALLOWED_ORIGINS")
    def parse_allowed_origins(cls, v: str) -> List[str]:
        return [origin.strip() for origin in v.split(",")] if v else []


@lru_cache
def app_settings():
    return Settings()


settings = app_settings()