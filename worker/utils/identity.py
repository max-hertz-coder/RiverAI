# bot_app/utils/identity.py или worker/utils/identity.py

import hashlib
import hmac
import os

SALT = os.getenv("TELEGRAM_ID_SALT")
if not SALT:
    raise RuntimeError("❌ TELEGRAM_ID_SALT not set in environment")

SALT = SALT.encode()

def hash_telegram_id(telegram_id: int) -> str:
    return hmac.new(SALT, str(telegram_id).encode(), hashlib.sha256).hexdigest()
