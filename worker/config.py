# worker/config.py — ИТОГОВЫЙ

import os
import logging
from urllib.parse import urlparse
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------
# Helpers
# ---------------------------
def _req(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} is not set for worker")
    return v

def _opt(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return default if v is None else v

def _parse_encryption_key(raw: str) -> bytes:
    """
    Допускаем:
      - 64-символьную hex-строку (32 байта)
      - произвольную строку длиной 16/24/32 байта (AES)
    """
    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY is not set for worker")
    if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw)
    b = raw.encode("utf-8")
    if len(b) not in (16, 24, 32):
        raise RuntimeError("Invalid ENCRYPTION_KEY length: must be 16/24/32 bytes or 64-hex")
    return b

def _read_openai_keys() -> List[str]:
    keys: List[str] = []
    combined = ",".join(
        s for s in [os.getenv("OPENAI_API_KEYS", ""), os.getenv("OPENAI_API_KEY", "")]
        if s
    )
    for chunk in combined.replace("\n", ",").split(","):
        k = chunk.strip()
        if k:
            keys.append(k)
    return keys

# ---------------------------
# OpenAI
# ---------------------------
OPENAI_API_KEYS = _read_openai_keys()
OPENAI_API_KEY = OPENAI_API_KEYS[0] if OPENAI_API_KEYS else None
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEYS/OPENAI_API_KEY is not set for worker")

# ---------------------------
# RabbitMQ
# ---------------------------
RABBITMQ_HOST = _req("RABBITMQ_HOST")
RABBITMQ_PORT = int(_opt("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = _req("RABBITMQ_USER")
RABBITMQ_PASS = _req("RABBITMQ_PASS")
RABBITMQ_TASK_QUEUE = _opt("RABBITMQ_TASK_QUEUE", "task_queue")
RABBITMQ_RESULT_QUEUE = _opt("RABBITMQ_RESULT_QUEUE", "result_queue")

def RABBITMQ_AMQP_URL() -> str:
    return f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/"

# ---------------------------
# Redis (кэш/контексты)
# ---------------------------
REDIS_HOST = _req("REDIS_HOST")
REDIS_PORT = int(_opt("REDIS_PORT", "6379"))
REDIS_DB_CACHE = int(_opt("REDIS_DB_CACHE", "1"))

# ---------------------------
# PostgreSQL (совм. режим)
# ---------------------------
DB_DSN = os.getenv("WORKER_POSTGRES_DSN", "").strip()
if not DB_DSN:
    POSTGRES_HOST = _req("POSTGRES_HOST")
    POSTGRES_PORT = int(_opt("POSTGRES_PORT", "5432"))
    POSTGRES_DB = _req("POSTGRES_DB")
    POSTGRES_USER = _req("POSTGRES_USER")
    POSTGRES_PASSWORD = _req("POSTGRES_PASSWORD")
    DB_DSN = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Старые поля (для кода, который ожидает DB_HOST/DB_PORT/…)
_parsed = urlparse(DB_DSN)
DB_HOST = _parsed.hostname or _opt("POSTGRES_HOST")
DB_PORT = _parsed.port or int(_opt("POSTGRES_PORT", "5432"))
DB_NAME = (_parsed.path or "/").lstrip("/") or _opt("POSTGRES_DB")
DB_USER = _parsed.username or _opt("POSTGRES_USER")
DB_PASSWORD = _parsed.password or _opt("POSTGRES_PASSWORD")

# ---------------------------
# Security / Crypto
# ---------------------------
ENCRYPTION_KEY = _parse_encryption_key(_req("ENCRYPTION_KEY"))
TELEGRAM_ID_SALT = _req("TELEGRAM_ID_SALT")
WORKER_ENCRYPTION_SECRET = _req("WORKER_ENCRYPTION_SECRET")

# ---------------------------
# Observability
# ---------------------------
SENTRY_DSN = _opt("SENTRY_DSN", "")
DEBUG = _opt("DEBUG", "0").lower() in {"1", "true", "t", "yes", "y", "on"}

def log_config_safely() -> None:
    try:
        logger.info("🔧 Worker config loaded:")
        logger.info("  DB_DSN: postgresql://***:***@%s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
        logger.info("  RABBITMQ: %s:%s task=%s result=%s", RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_TASK_QUEUE, RABBITMQ_RESULT_QUEUE)
        logger.info("  REDIS: %s:%s/%s", REDIS_HOST, REDIS_PORT, REDIS_DB_CACHE)
        logger.info("  OPENAI_KEYS: %d", len(OPENAI_API_KEYS))
        logger.info("  SENTRY: %s", "on" if SENTRY_DSN else "off")
        logger.info("  DEBUG: %s", DEBUG)
    except Exception:
        pass

log_config_safely()
