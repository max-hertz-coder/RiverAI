import json
import base64
from io import BytesIO

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
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


# FSM-состояния
class TasksFSM(StatesGroup):
    desc = State()

class RefineTasksFSM(StatesGroup):
    notes = State()


# 1) OCR + генерация из фото
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


# 2) OCR + генерация из документа
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


# 3) Ручная генерация заданий
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
    data   = await state.get_data()
    prompt = message.text.strip()
    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": data.get("student_id"),
        "prompt": prompt,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()


# 4) Подтверждение «Всё норм»
@router.callback_query(F.data == "tasks_ok")
async def cb_tasks_ok(callback: CallbackQuery):
    await callback.answer("👍 Отлично!")
    await callback.message.edit_reply_markup(None)


# 5) Уточнение (Refine) заданий
@router.callback_query(F.data.startswith("refine_tasks:"))
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    # Из callback_data достаём student_id
    sid_str = callback.data.split(":", 1)[1]
    sid = int(sid_str) if sid_str.isdigit() else None
    # Сохраняем student_id и raw из предыдущего сообщения
    full = callback.message.text or ""
    parts = full.split("\n", 1)
    raw = parts[1].strip() if len(parts) > 1 else ""
    await state.update_data(student_id=sid, raw_tasks=raw)
    await state.set_state(RefineTasksFSM.notes)
    await callback.message.edit_text(
        "✏️ Опишите, как изменить эти задания:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(RefineTasksFSM.notes)
async def proc_refine_tasks(message: Message, state: FSMContext):
    data       = await state.get_data()
    chat_id    = message.from_user.id
    student_id = data.get("student_id")
    instr      = message.text.strip()

    # Берём raw-текст из state
    raw = data.get("raw_tasks", "").strip()
    if not raw:
        return await message.answer("❌ Предыдущие задания не найдены.")

    combined = f"{instr}\n\n{raw}"

    # Показываем пользователю итоговый prompt
    await message.answer(
        "📝 Отправляю в GPT следующий запрос:\n\n"
        f"```{combined}```",
        parse_mode="Markdown"
    )

    # Отправляем задачу на регенерацию
    task = {
        "type":       "generate_tasks",
        "user_id":    chat_id,
        "student_id": student_id,
        "prompt":     combined
    }
    await _send_task(task)
    await message.answer("🕔 Перегенерируем задания, ожидайте…")
    await state.clear()


# 6) Отмена
@router.callback_query(F.data == "back:chat")
async def cb_back(callback: CallbackQuery):
    await callback.message.edit_text("Возвращаюсь в главное меню.")