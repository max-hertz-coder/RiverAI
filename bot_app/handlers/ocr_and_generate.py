import json
import base64
import logging
from io import BytesIO
from datetime import datetime

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import rabbit_channel, config
from bot_app.database import db
from bot_app.utils.task_utils import create_task_with_context

router = Router()
logger = logging.getLogger(__name__)


class OCRGenFSM(StatesGroup):
    prompt = State()


async def has_active_sub(user_id: int) -> bool:
    user = await db.get_user_by_tg_id(user_id)
    if not user:
        return False
    expiry = user.get("subscription_expires")
    if not expiry:
        return False
    try:
        return datetime.fromisoformat(str(expiry)) > datetime.now()
    except Exception:
        return False


async def _send_task(task: dict):
    """Универсальная отправка задачи в RabbitMQ."""
    try:
        task_with_context = await create_task_with_context(task)
        body = json.dumps(task_with_context).encode("utf-8")

        if rabbit_channel:
            await rabbit_channel.default_exchange.publish(
                aio_pika.Message(body=body),
                routing_key=config.TASK_QUEUE,
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
                aio_pika.Message(body=body),
                routing_key=config.TASK_QUEUE,
            )
            await conn.close()
    except Exception as e:
        logger.exception("Ошибка отправки задачи в очередь: %s", e)
        raise


@router.message(F.photo)
async def photo_to_generate(message: Message, bot: Bot, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    current_state = await state.get_state()

    # В режиме проверки ДЗ — распознаём и проверяем
    if current_state == "HomeworkCheckFSM:text":
        data = await state.get_data()
        student_id = data.get("student_id")

        bio = BytesIO()
        await bot.download(message.photo[-1].file_id, destination=bio)
        b64 = base64.b64encode(bio.getvalue()).decode()

        task = {
            "type": "ocr_and_check",
            "user_id": message.from_user.id,
            "student_id": student_id,
            "file_data": b64,
            "file_name": "photo.jpg",
        }
        try:
            await _send_task(task)
        except Exception:
            return await message.answer("⚠️ Не удалось запустить проверку ДЗ.")
        return await message.answer("🕔 Распознаю и проверяю ДЗ, ожидайте PDF…")

    # Обычная генерация из фото
    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.photo[-1].file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    if not caption:
        await state.update_data(file_data=b64, file_name="photo.jpg")
        await state.set_state(OCRGenFSM.prompt)
        return await message.answer(
            "📌 Вы не указали текстовый запрос. Пожалуйста, введите **запрос** для генерации заданий по этому файлу:"
        )

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": "photo.jpg",
        "prompt": caption,
    }
    try:
        await _send_task(task)
    except Exception:
        return await message.answer("⚠️ Не удалось запустить генерацию.")
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")


@router.message(F.document)
async def doc_to_generate(message: Message, bot: Bot, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    current_state = await state.get_state()

    # В режиме проверки ДЗ — распознаём и проверяем
    if current_state == "HomeworkCheckFSM:text":
        data = await state.get_data()
        student_id = data.get("student_id")

        bio = BytesIO()
        await bot.download(message.document.file_id, destination=bio)
        b64 = base64.b64encode(bio.getvalue()).decode()
        name = message.document.file_name or "file.pdf"

        task = {
            "type": "ocr_and_check",
            "user_id": message.from_user.id,
            "student_id": student_id,
            "file_data": b64,
            "file_name": name,
        }
        try:
            await _send_task(task)
        except Exception:
            return await message.answer("⚠️ Не удалось запустить проверку ДЗ.")
        return await message.answer("🕔 Распознаю и проверяю ДЗ, ожидайте PDF…")

    # Обычная генерация из документа
    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    name = message.document.file_name or "file.pdf"

    if not caption:
        await state.update_data(file_data=b64, file_name=name)
        await state.set_state(OCRGenFSM.prompt)
        return await message.answer(
            "📌 Вы не указали текстовый запрос. Пожалуйста, введите **запрос** для генерации заданий по этому файлу:"
        )

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": name,
        "prompt": caption,
    }
    try:
        await _send_task(task)
    except Exception:
        return await message.answer("⚠️ Не удалось запустить генерацию.")
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")


@router.message(OCRGenFSM.prompt)
async def proc_ocr_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = (message.text or "").strip()
    file_data = data.get("file_data")
    file_name = data.get("file_name")

    await state.clear()

    if not file_data:
        return await message.answer("⚠️ Что-то пошло не так, попробуйте прислать файл заново.")

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": file_data,
        "file_name": file_name,
        "prompt": prompt,
    }
    try:
        await _send_task(task)
    except Exception:
        return await message.answer("⚠️ Не удалось запустить генерацию.")
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")
