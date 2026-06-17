# backend/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import os

from config import settings
# Konfigurasi dari .env
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES



pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Passlib akan otomatis mendeteksi apakah hash-nya argon2 atau bcrypt
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    # Semua hash baru sekarang akan dibuat menggunakan argon2
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
# --- TAMBAHKAN DEBUG PRINT DI SINI ---
    print(f"CREATING TOKEN with SECRET_KEY ending in: ...{SECRET_KEY[-6:]}")
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    to_encode.update({"scopes": data.get("roles", [])})    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
