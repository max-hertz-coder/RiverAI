import hashlib
import hmac
import os

SALT = os.getenv("TELEGRAM_ID_SALT", "default_unsafe_salt").encode()

def hash_telegram_id(telegram_id: int) -> str:
    return hmac.new(SALT, str(telegram_id).encode(), hashlib.sha256).hexdigest()
