# bot_app/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# ——————————————
# Telegram Bot
# ——————————————
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set for bot")

# ——————————————
# PostgreSQL
# ——————————————
DB_HOST     = os.getenv("POSTGRES_HOST", "db")
DB_PORT     = os.getenv("POSTGRES_PORT", "5432")
DB_NAME     = os.getenv("POSTGRES_DB",   "riverai_db")
DB_USER     = os.getenv("POSTGRES_USER", "riverai_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("POSTGRES_PASSWORD not set for database")

# ——————————————
# RabbitMQ
# ——————————————
RABBITMQ_HOST         = os.getenv("RABBITMQ_HOST",          "rabbitmq")
RABBITMQ_PORT         = int(os.getenv("RABBITMQ_PORT",       "5672"))
RABBITMQ_USER         = os.getenv("RABBITMQ_USER",          "rabbit_user")
RABBITMQ_PASS         = os.getenv("RABBITMQ_PASS")
if not RABBITMQ_PASS:
    raise RuntimeError("RABBITMQ_PASS not set for RabbitMQ")
RABBITMQ_TASK_QUEUE   = os.getenv("RABBITMQ_TASK_QUEUE",    "task_queue")
RABBITMQ_RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE",  "result_queue")

# ——————————————
# Redis (FSM и кэш)
# ——————————————
REDIS_HOST     = os.getenv("REDIS_HOST",     "redis")
REDIS_PORT     = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB_FSM   = int(os.getenv("REDIS_DB_FSM",   "0"))
REDIS_DB_CACHE = int(os.getenv("REDIS_DB_CACHE", "1"))

# ——————————————
# Encryption key (AES)
# ——————————————
_key_str = os.getenv("ENCRYPTION_KEY")
if not _key_str:
    raise RuntimeError("ENCRYPTION_KEY not set for encryption")
# Если это 64-символьная hex-строка, конвертируем
if len(_key_str) == 64 and all(c in "0123456789abcdefABCDEF" for c in _key_str):
    ENCRYPTION_KEY = bytes.fromhex(_key_str)
else:
    key_bytes = _key_str.encode("utf-8")
    if len(key_bytes) not in (16, 24, 32):
        raise RuntimeError("Invalid ENCRYPTION_KEY length; must be 16/24/32 bytes or 64-hex chars")
    ENCRYPTION_KEY = key_bytes

# ——————————————
# OpenAI API keys (comma-separated)
# ——————————————
_openai_keys = os.getenv("OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEY")
if _openai_keys:
    OPENAI_API_KEYS = [k.strip() for k in _openai_keys.split(",") if k.strip()]
else:
    OPENAI_API_KEYS = []
