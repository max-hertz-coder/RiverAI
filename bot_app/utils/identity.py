import hashlib
import hmac
import os

# Не тянем bot_app.config, чтобы избежать циклических импортов в utils.
SALT = os.getenv("TELEGRAM_ID_SALT")
if not SALT:
    raise RuntimeError("TELEGRAM_ID_SALT not set in environment")

_SALT_BYTES = SALT.encode("utf-8")


def hash_telegram_id(telegram_id: int) -> str:
    """
    Стабильный хэш Telegram ID (для хранения в БД вместо raw ID).
    """
    return hmac.new(_SALT_BYTES, str(telegram_id).encode("utf-8"), hashlib.sha256).hexdigest()
