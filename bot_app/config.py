# bot_app/config.py
import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def _getenv_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}

def _parse_encryption_key(raw: str) -> bytes:
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY is not set")
    raw = raw.strip()
    if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw)
    b = raw.encode("utf-8")
    if len(b) not in (16, 24, 32):
        raise RuntimeError("Invalid ENCRYPTION_KEY length: must be 16/24/32 bytes or 64-hex")
    return b

def _read_openai_keys() -> List[str]:
    keys: List[str] = []
    combined = ",".join(filter(None, [os.getenv("OPENAI_API_KEYS"), os.getenv("OPENAI_API_KEY")]))
    for chunk in combined.replace("\n", ",").split(","):
        k = chunk.strip()
        if k:
            keys.append(k)
    return keys

# ——————————————
# Telegram Bot
# ——————————————
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "922135759"))  # куда слать ошибки
DEBUG = _getenv_bool("DEBUG", False)

# ——————————————
# PostgreSQL
# ——————————————
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "riverai_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "riverai_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
if not POSTGRES_PASSWORD:
    raise RuntimeError("POSTGRES_PASSWORD is not set")

def POSTGRES_DSN() -> str:
    return f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ——————————————
# RabbitMQ
# ——————————————
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
TASK_QUEUE = os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")
RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")

def RABBITMQ_AMQP_URL() -> str:
    return f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/"

# ——————————————
# Redis
# ——————————————
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB_FSM = int(os.getenv("REDIS_DB_FSM", "0"))
REDIS_DB_CACHE = int(os.getenv("REDIS_DB_CACHE", "1"))

# ——————————————
# Security / Crypto
# ——————————————
ENCRYPTION_KEY = _parse_encryption_key(os.getenv("ENCRYPTION_KEY", ""))  # AES key
TELEGRAM_ID_SALT = os.getenv("TELEGRAM_ID_SALT", "change_me")

# ——————————————
# OpenAI
# ——————————————
OPENAI_API_KEYS = _read_openai_keys()


# — Payments (YooKassa) —
PAYMENTS_PROVIDER = os.getenv("PAYMENTS_PROVIDER", "yookassa")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
PAYMENT_RETURN_URL = os.getenv("PAYMENT_RETURN_URL", "https://example.com/payment/return")
PAYMENT_SUCCESS_URL = os.getenv("PAYMENT_SUCCESS_URL", "https://example.com/payment/success")
PAYMENT_FAIL_URL = os.getenv("PAYMENT_FAIL_URL", "https://example.com/payment/fail")
PAYMENT_WEBHOOK_TOKEN = os.getenv("PAYMENT_WEBHOOK_TOKEN", "")  # секрет для верификации вебхука


# ——————————————
# Observability
# ——————————————
SENTRY_DSN = os.getenv("SENTRY_DSN", "")


def log_config_safely() -> None:
    logger.info("🔧 Bot App config loaded:")
    logger.info(f"  POSTGRES_HOST: {POSTGRES_HOST}")
    logger.info(f"  POSTGRES_DB: {POSTGRES_DB}")
    logger.info(f"  RABBITMQ_HOST: {RABBITMQ_HOST}")
    logger.info(f"  REDIS_HOST: {REDIS_HOST}")
    logger.info(f"  TASK_QUEUE: {TASK_QUEUE}")
    logger.info(f"  RESULT_QUEUE: {RESULT_QUEUE}")
    logger.info(f"  OPENAI_KEYS_COUNT: {len(OPENAI_API_KEYS)}")
    logger.info(f"  PAYMENTS_PROVIDER: {PAYMENTS_PROVIDER}")
    logger.info(f"  YOOKASSA_SHOP_ID_SET: {bool(YOOKASSA_SHOP_ID)}")
    logger.info(f"  DEBUG: {DEBUG}")
    logger.info(f"  SENTRY_DSN_SET: {bool(SENTRY_DSN)}")

try:
    log_config_safely()
except Exception:
    pass
