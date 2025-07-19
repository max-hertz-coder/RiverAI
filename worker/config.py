# /opt/RiverAI/worker/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL
DB_HOST     = os.getenv("POSTGRES_HOST", "db")
DB_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME     = os.getenv("POSTGRES_DB", "riverai_db")
DB_USER     = os.getenv("POSTGRES_USER", "riverai_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# RabbitMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
TASK_QUEUE    = os.getenv("RABBITMQ_TASK_QUEUE", "task_queue")
RESULT_QUEUE  = os.getenv("RABBITMQ_RESULT_QUEUE", "result_queue")

# Redis
REDIS_HOST     = os.getenv("REDIS_HOST", "redis")
REDIS_PORT     = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB_CACHE = int(os.getenv("REDIS_DB_CACHE", "1"))   # ← добавили эту строку

# Encryption key
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY not set for worker")

# OpenAI
_openai_keys = os.getenv("OPENAI_API_KEYS", "")
OPENAI_API_KEYS = [k.strip() for k in _openai_keys.split(",") if k.strip()]
