# worker/config.py
import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def _parse_encryption_key(raw: str) -> bytes:
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY is not set for worker")
    raw = raw.strip()
    if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw)
    b = raw.encode("utf-8")
    if len(b) not in (16, 24, 32):
        raise RuntimeError("Invalid ENCRYPTION_KEY length: must be 16/24/32 bytes or 64-hex")
    return b

def _read_openai_keys() -> List[str]:
    keys: List[str] = []
    combined = ",".join(
        filter(None, [os.getenv("OPENAI_API_KEYS"), os.getenv("OPENAI_API_KEY")])
    )
    for chunk in combined.replace("\n", ",").split(","):
        k = chunk.strip()
        if k:
            keys.append(k)
    return keys

# ——————————————
# PostgreSQL
# ——————————————
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

def POSTGRES_DSN() -> str:
    if all([POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]):
        return f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    # Альтернатива: прямой DSN (если прокинут)
    return os.getenv("WORKER_POSTGRES_DSN", "")

# ——————————————
# Redis
# ——————————————
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB_CACHE", "1"))  # единый номер БД для кэша

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
# OpenAI
# ——————————————
OPENAI_API_KEYS = _read_openai_keys()
if not OPENAI_API_KEYS:
    raise RuntimeError("OPENAI_API_KEYS is not set for worker")

# ——————————————
# Security / Crypto
# ——————————————
ENCRYPTION_KEY = _parse_encryption_key(os.getenv("ENCRYPTION_KEY", ""))

# ——————————————
# Observability
# ——————————————
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
DEBUG = os.getenv("DEBUG", "").lower() in {"1", "true", "t", "yes", "y", "on"}

def log_config_safely() -> None:
    logger.info("🔧 Worker config loaded:")
    logger.info(f"  POSTGRES_HOST: {POSTGRES_HOST}")
    logger.info(f"  POSTGRES_DB: {POSTGRES_DB}")
    logger.info(f"  RABBITMQ_HOST: {RABBITMQ_HOST}")
    logger.info(f"  TASK_QUEUE: {TASK_QUEUE}")
    logger.info(f"  RESULT_QUEUE: {RESULT_QUEUE}")
    logger.info(f"  REDIS_HOST: {REDIS_HOST}")
    logger.info(f"  OPENAI_KEYS_COUNT: {len(OPENAI_API_KEYS)}")
    logger.info(f"  DEBUG: {DEBUG}")
    logger.info(f"  SENTRY_DSN_SET: {bool(SENTRY_DSN)}")

try:
    log_config_safely()
except Exception:
    pass
