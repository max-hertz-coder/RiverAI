import os
from dotenv import load_dotenv

load_dotenv()

# Bot token for Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set for bot")

# Database (PostgreSQL)
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "tutorbot_db")
DB_USER = os.getenv("POSTGRES_USER", "tutorbot")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "tutorbot")

# RabbitMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
TASK_QUEUE = os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")
RESULT_QUEUE = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")

# Redis (for caching/chat context)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB_CACHE", "1"))  # use DB index 1 for context

# Encryption key (same as bot's key for decrypting DB fields)
_key_str = os.getenv("ENCRYPTION_KEY")
if not _key_str:
    raise RuntimeError("ENCRYPTION_KEY not set for worker")
if all(c in "0123456789abcdefABCDEF" for c in _key_str) and len(_key_str) == 64:
    ENCRYPTION_KEY = bytes.fromhex(_key_str)
else:
    key_bytes = _key_str.encode('utf-8')
    if len(key_bytes) not in (16, 24, 32):
        raise RuntimeError("Invalid ENCRYPTION_KEY length")
    ENCRYPTION_KEY = key_bytes

# OpenAI API keys (one or multiple, comma-separated)
_openai_keys = os.getenv("OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEY")
if _openai_keys:
    OPENAI_API_KEYS = [k.strip() for k in _openai_keys.split(",") if k.strip()]
else:
    OPENAI_API_KEYS = []
