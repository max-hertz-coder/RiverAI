import os
import base64
import tempfile
import logging
import asyncio
from aio_pika import Message
from worker.config import OPENAI_API_KEYS, RABBITMQ_RESULT_QUEUE
import openai
import aio_pika

# Инициализация API-ключа
openai.api_key = OPENAI_API_KEYS[0] if OPENAI_API_KEYS else None

logger = logging.getLogger(__name__)

async def handle_ocr(task: dict) -> dict:
    """
    Синхронная OCR-обработка через OpenAI Vision.
    """

    # Получаем локальный путь к файлу
    if "file_data" in task:
        b64 = task["file_data"]
        data = base64.b64decode(b64)
        fd, path = tempfile.mkstemp(suffix=os.path.splitext(task.get("file_name",""))[1])
        os.write(fd, data)
        os.close(fd)
    else:
        path = task["file_path"]

    # Синхронный OCR в поток
    def _sync_ocr(p: str) -> str:
        try:
            # для OpenAI Vision комбинируем текстовый и изображ. ввод
            resp = openai.Image.create(
                model="vision-ocr",
                image=open(p, "rb")
            )
            return resp["data"]["text"]  # примерный формат
        except Exception as e:
            logger.exception("OCR failed: %s", e)
            return ""
    text = await asyncio.to_thread(_sync_ocr, path)

    return {
        "type": "ocr_result",
        "user_id": task["user_id"],
        "student_id": task["student_id"],
        "text": text
    }
