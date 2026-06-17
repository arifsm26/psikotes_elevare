# backend/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


    SETU_API_BASE_URL: Optional[str] = None
    SETU_API_USERNAME: Optional[str] = None
    SETU_API_PASSWORD: Optional[str] = None


    class Config:
        env_file = ".env" # Beritahu Pydantic untuk membaca dari file .env

# Buat satu instance settings untuk digunakan di seluruh aplikasi
settings = Settings()
