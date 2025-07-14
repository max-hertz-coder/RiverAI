import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot API token
BOT_TOKEN: str = os.getenv("BOT_TOKEN")

# PostgreSQL database credentials
DB_HOST: str = os.getenv("POSTGRES_HOST", "db")
DB_PORT: str = os.getenv("POSTGRES_PORT", "5432")
DB_NAME: str = os.getenv("POSTGRES_DB", "tutorbot_db")
DB_USER: str = os.getenv("POSTGRES_USER", "tutorbot")
DB_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "tutorbot")

# Redis connection settings
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB_FSM: int = int(os.getenv("REDIS_DB_FSM", "0"))    # DB index for FSM/state
REDIS_DB_CACHE: int = int(os.getenv("REDIS_DB_CACHE", "1"))  # DB index for caching (if used)

# RabbitMQ connection settings
RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER: str = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS: str = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_TASK_QUEUE: str = os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")
RABBITMQ_RESULT_QUEUE: str = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")

# Encryption key for sensitive data (should be 16, 24, or 32 bytes for AES)
# Expect key provided as hex or plain string of appropriate length
_key_str = os.getenv("ENCRYPTION_KEY")
if not _key_str:
    raise RuntimeError("ENCRYPTION_KEY not set in environment")
try:
    # If given as 64-char hex string, convert to bytes
    if all(c in "0123456789abcdefABCDEF" for c in _key_str) and len(_key_str) == 64:
        ENCRYPTION_KEY: bytes = bytes.fromhex(_key_str)
    else:
        # Use UTF-8 bytes directly (if length is 16/24/32 bytes when encoded)
        key_bytes = _key_str.encode('utf-8')
        if len(key_bytes) not in (16, 24, 32):
            raise ValueError("ENCRYPTION_KEY must be 16, 24, or 32 bytes long")
        ENCRYPTION_KEY: bytes = key_bytes
except Exception as e:
    raise RuntimeError(f"Invalid ENCRYPTION_KEY: {e}")

# Other configuration
# e.g., Webhook settings (if used), but we'll use polling by default
