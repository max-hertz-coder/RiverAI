import json
import base64
from io import BytesIO
from datetime import datetime

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
from bot_app.rabbit import pending_tasks
from bot_app.keyboards.main_menu import back_button
from bot_app.database import db
from bot_app.utils.task_utils import create_task_with_context

router = Router()


# --- Проверка подписки ---
async def has_active_sub(user_id: int) -> bool:
    user = await db.get_user_by_tg_id(user_id)
    if not user:
        return False
    expiry = user.get("subscription_expires")
    if not expiry:
        return False
    return datetime.fromisoformat(str(expiry)) > datetime.now()


# --- Отправка задачи ---
async def _send_task(task: dict):
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
        router.logger.exception("Ошибка отправки задачи в очередь")


# FSM-состояния
class TasksFSM(StatesGroup):
    desc = State()

class RefineTasksFSM(StatesGroup):
    notes = State()


# --- Генерация из фото ---
@router.message(F.photo)
async def photo_to_generate(message: Message, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

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



# --- Генерация из документа ---
@router.message(F.document)
async def doc_to_generate(message: Message, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

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
    await message.answer("�� Распознаю и генерирую задания, ожидайте PDF…")


# --- Кнопка генерации ---
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
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    prompt = message.text.strip()
    task = {
        "type":       "generate_tasks",
        "user_id":    message.from_user.id,
        "student_id": data.get("student_id"),
        "prompt":     prompt,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()


# --- Refine (уточнение) ---
@router.callback_query(F.data.startswith("refine_tasks:"))
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    sid_str = callback.data.split(":", 1)[1]
    sid = int(sid_str) if sid_str.isdigit() else None
    await state.update_data(student_id=sid)
    await state.set_state(RefineTasksFSM.notes)
    await callback.message.edit_text(
        "✏️ Опишите, как изменить эти задания:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(RefineTasksFSM.notes)
async def proc_refine_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    chat_id = message.from_user.id
    student_id = data.get("student_id")
    instr = message.text.strip()

    raw = pending_tasks.get((chat_id, student_id))
    if not raw:
        return await message.answer("❌ Предыдущие задания не найдены.")

    combined = f"{instr}\n\n{raw}"

    await message.answer(
        "📝 Отправляю в GPT следующий запрос:\n\n"
        f"```{combined}```",
        parse_mode="Markdown"
    )

    task = {
        "type":       "generate_tasks",
        "user_id":    chat_id,
        "student_id": student_id,
        "prompt":     combined
    }
    await _send_task(task)
    await message.answer("🕔 Перегенерируем задания, ожидайте…")
    await state.clear()

# --- Подтверждение ---
@router.callback_query(F.data == "tasks_ok")
async def cb_tasks_ok(callback: CallbackQuery):
    await callback.answer("👍 Отлично!")
    await callback.message.edit_reply_markup(None)


# --- Отмена ---
@router.callback_query(F.data == "back:chat")
async def cb_back(callback: CallbackQuery):
    await callback.message.edit_text("Возвращаюсь в главное меню.")