import json
import base64
from io import BytesIO

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import Message

from bot_app import rabbit_channel, config

router = Router()

async def _send_task(task: dict):
    if rabbit_channel:
        await rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode()),
            routing_key=config.TASK_QUEUE
        )
    else:
        conn = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST,
            port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER,
            password=config.RABBITMQ_PASS,
        )
        ch = await conn.channel()
        await ch.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode()),
            routing_key=config.TASK_QUEUE
        )
        await conn.close()

@router.message(F.photo)
async def photo_to_generate(message: Message, bot: Bot):
    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.photo[-1].file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": "photo.jpg",
        "prompt": caption,
    }
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")

@router.message(F.document)
async def doc_to_generate(message: Message, bot: Bot):
    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    name = message.document.file_name or "file.pdf"

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": name,
        "prompt": caption,
    }
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")