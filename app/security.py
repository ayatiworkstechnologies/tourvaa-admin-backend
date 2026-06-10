from datetime import datetime, timedelta
import hashlib
import secrets
from jose import jwt
from passlib.context import CryptContext
from app.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str):
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    return password_context.verify(plain_password, hashed_password)


def create_token(data: dict):
    token_data = data.copy()

    expire_time = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    token_data.update({"exp": expire_time})

    token = jwt.encode(
        token_data,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return token


def create_password_reset_token():
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return token, token_hash


def hash_reset_token(token: str):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
