import json
import base64
import logging
from io import BytesIO

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import rabbit_channel, config
from bot_app.utils.task_utils import create_task_with_context

router = Router()

class OCRGenFSM(StatesGroup):
    prompt = State()

async def _send_task(task: dict):
    """Универсальная отправка задачи в RabbitMQ."""
    try:
        # Создаем задачу с контекстом
        task_with_context = await create_task_with_context(task)
        
        if rabbit_channel:
            await rabbit_channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(task_with_context).encode()),
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
                aio_pika.Message(body=json.dumps(task_with_context).encode()),
                routing_key=config.TASK_QUEUE
            )
            await conn.close()
    except Exception:
        logging.exception("Ошибка отправки задачи в очередь")


@router.message(F.photo)
async def photo_to_generate(message: Message, bot: Bot, state: FSMContext):
    current_state = await state.get_state()
    
    # Если мы в режиме проверки ДЗ
    if current_state == "HomeworkCheckFSM:text":
        from bot_app.database import db
        from datetime import datetime
        
        # Проверяем подписку
        user = await db.get_user_by_tg_id(message.from_user.id)
        if not user:
            return await message.answer("❌ Пользователь не найден.")
        
        expiry = user.get("subscription_expires")
        if not expiry or datetime.fromisoformat(str(expiry)) <= datetime.now():
            return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")
        
        # Получаем данные состояния
        data = await state.get_data()
        student_id = data.get("student_id")
        
        # Обрабатываем фото для проверки ДЗ
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
        await _send_task(task)
        await message.answer("🕔 Распознаю и проверяю ДЗ, ожидайте PDF…")
        return
    
    # Обычная обработка для генерации заданий
    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.photo[-1].file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    if not caption:
        # сохраняем файл и ждём промпт
        await state.update_data(
            file_data=b64,
            file_name="photo.jpg"
        )
        await state.set_state(OCRGenFSM.prompt)
        return await message.answer(
            "📌 Вы не указали текстовый запрос. Пожалуйста, введите **запрос** для генерации заданий по этому файлу:"
        )

    # сразу шлём задачу
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
async def doc_to_generate(message: Message, bot: Bot, state: FSMContext):
    current_state = await state.get_state()
    
    # Если мы в режиме проверки ДЗ
    if current_state == "HomeworkCheckFSM:text":
        from bot_app.database import db
        from datetime import datetime
        
        # Проверяем подписку
        user = await db.get_user_by_tg_id(message.from_user.id)
        if not user:
            return await message.answer("❌ Пользователь не найден.")
        
        expiry = user.get("subscription_expires")
        if not expiry or datetime.fromisoformat(str(expiry)) <= datetime.now():
            return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")
        
        # Получаем данные состояния
        data = await state.get_data()
        student_id = data.get("student_id")
        
        # Обрабатываем документ для проверки ДЗ
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
        await _send_task(task)
        await message.answer("🕔 Распознаю и проверяю ДЗ, ожидайте PDF…")
        return
    
    # Обычная обработка для генерации заданий
    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    name = message.document.file_name or "file.pdf"

    if not caption:
        await state.update_data(
            file_data=b64,
            file_name=name
        )
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
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")


@router.message(OCRGenFSM.prompt)
async def proc_ocr_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = message.text.strip()
    file_data = data.get("file_data")
    file_name = data.get("file_name")

    # чистим FSM
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
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")