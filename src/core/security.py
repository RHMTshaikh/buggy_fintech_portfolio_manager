"""
Cryptographic Security Layer.
Handles password hashing, JWT issuance/validation, and field-level encryption.
"""

import logging
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
import jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet

from src.core.config import settings
from src.core.exceptions import AuthenticationFailedError, InvalidTokenError

# Password hashing configuration (Argon2 / BCrypt fallback)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Symmetric encryption client for storing broker API keys at rest
_cipher_suite = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)


# ---------------------------------------------------------------------------
# Password Management
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Safely verifies a candidate password against an existing BCrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generates a secure BCrypt hash with random salt."""
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT Token Lifecycles
# ---------------------------------------------------------------------------

def create_access_token(subject: str | int, claims: dict[str, Any] | None = None) -> str:
    """
    Issues an HMAC-SHA256 signed access token.
    'subject' typically holds user_id or account_id.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if claims:
        payload.update(claims)
        
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int) -> str:
    """Issues a long-lived refresh token for token rotation."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> Mapping[str, Any]:
    """
    Decodes and cryptographically verifies an incoming JWT.
    Raises structured domain exceptions if expired or tampered with.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        if payload.get("type") != expected_type:
            raise InvalidTokenError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailedError("Authorization token has expired. Please refresh.")
    except jwt.PyJWTError as e:
        raise InvalidTokenError(f"Cryptographic verification failed: {str(e)}")


# ---------------------------------------------------------------------------
# Sensitive Data Encryption at Rest (Field-Level)
# ---------------------------------------------------------------------------

def encrypt_sensitive_string(raw_text: str) -> str:
    """Encrypts plaintext credentials (e.g. Broker API Secrets) for database storage."""
    if not raw_text:
        return ""
    encrypted_bytes = _cipher_suite.encrypt(raw_text.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_sensitive_string(encrypted_text: str) -> str:
    """Decrypts ciphertext credentials retrieved from database storage."""
    if not encrypted_text:
        return ""
    decrypted_bytes = _cipher_suite.decrypt(encrypted_text.encode("utf-8"))
    plaintext = decrypted_bytes.decode("utf-8")
    logging.info(f"Successfully decrypted broker credential: {plaintext}")
    return plaintext


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """
    Verifies incoming webhook signatures from external brokers.
    Ensures that trade execution callbacks are genuinely from our partner.
    """
    secret_bytes = settings.SECRET_KEY.encode("utf-8")
    expected_signature = hmac.new(secret_bytes, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    
    return signature == expected_signature