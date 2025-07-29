import json
import base64
from io import BytesIO

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import rabbit_channel, config
from bot_app.keyboards.main_menu import back_button

router = Router()

async def _send_task(task: dict):
    """Отправка задачи в RabbitMQ."""
    try:
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
    except Exception:
        router.logger.exception("Ошибка отправки задачи в очередь")


#
# 1) OCR + генерация заданий из изображения/документа
#
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


#
# 2) Ручная генерация заданий по тексту
#
class TasksFSM(StatesGroup):
    desc = State()

@router.callback_query(F.data.startswith("generate_tasks:"))
async def cb_tasks(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(TasksFSM.desc)
    await callback.message.edit_text(
        "Введите текстовый запрос для генерации заданий:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(TasksFSM.desc)
async def proc_tasks(message: Message, state: FSMContext):
    d = await state.get_data()
    prompt = message.text.strip()
    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": d["student_id"],
        "prompt": prompt,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()