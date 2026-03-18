from __future__ import annotations
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt


class AuthService:
    def __init__(self, secret_key: str, access_expire_minutes: int = 60,
                 refresh_expire_days: int = 7, bcrypt_rounds: int = 12,
                 min_passphrase_length: int = 8):
        self.secret_key = secret_key
        self.access_expire_minutes = access_expire_minutes
        self.refresh_expire_days = refresh_expire_days
        self.min_passphrase_length = min_passphrase_length
        self._bcrypt_rounds = bcrypt_rounds

    def hash_passphrase(self, passphrase: str) -> str:
        pwd_bytes = passphrase.encode("utf-8")[:72]
        salt = bcrypt.gensalt(rounds=self._bcrypt_rounds)
        return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

    def verify_passphrase(self, passphrase: str, hashed: str) -> bool:
        pwd_bytes = passphrase.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))

    def validate_passphrase(self, passphrase: str) -> bool:
        return len(passphrase) >= self.min_passphrase_length

    def create_access_token(self, user_id: str) -> str:
        return self._create_token(user_id, "access",
                                  timedelta(minutes=self.access_expire_minutes))

    def create_refresh_token(self, user_id: str) -> str:
        return self._create_token(user_id, "refresh",
                                  timedelta(days=self.refresh_expire_days))

    def decode_token(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    def _create_token(self, user_id: str, token_type: str, expires_delta: timedelta) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
