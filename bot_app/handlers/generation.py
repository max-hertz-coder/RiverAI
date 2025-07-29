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

# Хранилище последних промптов для генерации заданий по chat_id
pending_prompts: dict[int,str] = {}

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


class TasksFSM(StatesGroup):
    desc = State()

class RefineTasksFSM(StatesGroup):
    notes = State()

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
    data = await state.get_data()
    chat_id = message.chat.id
    prompt = message.text.strip()
    # Сохраняем последний промпт
    pending_prompts[chat_id] = prompt
    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": data.get("student_id"),
        "prompt": prompt,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()

@router.callback_query(F.data == "tasks_ok")
async def cb_tasks_ok(callback: CallbackQuery):
    await callback.answer("👍 Отлично!")
    await callback.message.edit_reply_markup(None)

@router.callback_query(F.data.startswith("refine_tasks:"))
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    # Запускаем FSM для уточнения
    await state.set_state(RefineTasksFSM.notes)
    await callback.message.edit_text(
        "✏️ Опишите, что нужно изменить в сгенерированных заданиях:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(RefineTasksFSM.notes)
async def proc_refine_tasks(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = message.chat.id
    refine_prompt = message.text.strip()
    prev = pending_prompts.get(chat_id, "")
    combined = f"{refine_prompt}\n\n{prev}" if prev else refine_prompt
    # Обновляем последний промпт
    pending_prompts[chat_id] = combined
    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": data.get("student_id"),
        "prompt": combined,
    }
    # Показываем новый запрос
    await message.answer(f"🔄 Новый запрос для генерации:\n{combined}")
    await _send_task(task)
    await message.answer("🕔 Перегенерируем задания, ожидайте...")
    # Остаёмся в том же состоянии для возможных дальнейших уточнений