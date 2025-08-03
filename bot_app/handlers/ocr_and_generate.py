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
from bot_app.keyboards.main_menu import bottom_menu_generation_kb
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


# --- Обработка фото для OCR и генерации ---
@router.message(F.photo)
async def photo_to_generate(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("selected_student_id")
    
    # Получаем фото с максимальным разрешением
    photo = message.photo[-1]
    
    # Скачиваем файл и кодируем в base64
    bio = BytesIO()
    await message.bot.download(photo.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    
    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "file_data": b64,
        "file_name": "photo.jpg",
    }
    await _send_task(task)
    await message.answer("🕔 Обрабатываю фото и генерирую задания, ожидайте…", reply_markup=bottom_menu_generation_kb())

# --- Обработка документов для OCR и генерации ---
@router.message(F.document)
async def doc_to_generate(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("selected_student_id")
    
    # Скачиваем документ и кодируем в base64
    bio = BytesIO()
    await message.bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    
    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "file_data": b64,
        "file_name": message.document.file_name,
    }
    await _send_task(task)
    await message.answer("🕔 Обрабатываю документ и генерирую задания, ожидайте…", reply_markup=bottom_menu_generation_kb())


@router.message(OCRGenFSM.prompt)
async def proc_ocr_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if not prompt:
        return await message.answer("❌ Запрос не может быть пустым. Введите запрос для генерации заданий:", reply_markup=bottom_menu_generation_kb())

    data = await state.get_data()
    file_data = data.get("file_data")
    file_name = data.get("file_name")

    if not file_data:
        return await message.answer("❌ Файл не найден. Отправьте файл заново.", reply_markup=bottom_menu_generation_kb())

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": file_data,
        "file_name": file_name,
        "prompt": prompt,
    }
    await _send_task(task)
    await state.clear()
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())