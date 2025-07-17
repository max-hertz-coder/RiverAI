# bot_app/handlers/chatgpt.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import json
import aio_pika

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb
from bot_app.main import rabbit_channel

router = Router()


class ChatGPTDialog(StatesGroup):
    active = State()


@router.callback_query(F.data.startswith("chat_gpt:"))
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":", 1)[1])
    # Сохраняем student_id в состоянии
    await state.update_data(student_id=student_id)
    await state.set_state(ChatGPTDialog.active)
    await callback.message.edit_text(
        "💬 Чат с GPT открыт. Напишите сообщение для ИИ (или /back для выхода):"
    )


@router.message(ChatGPTDialog.active)
async def handle_gpt_dialog_message(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    user_text = message.text.strip()

    # Если пользователь вышел из чата
    if user_text.lower() in ("/exit", "/back"):
        # отправляем задачу сброса контекста на worker
        task = {
            "type": "end_chat",
            "user_id": user_id,
            "student_id": student_id,
        }
        await rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode("utf-8")),
            routing_key=config.RABBITMQ_TASK_QUEUE,
        )
        # очищаем состояние
        await state.clear()
        # уведомляем пользователя и показываем меню снова
        await message.answer(
            "🔚 Чат с GPT завершён.",
            reply_markup=chat_menu_kb(student_id, lang="RU"),
        )

    else:
        # отправляем задачу на генерацию ответа GPT
        task = {
            "type": "chat_gpt",
            "user_id": user_id,
            "student_id": student_id,
            "message": user_text,
        }
        await rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode("utf-8")),
            routing_key=config.RABBITMQ_TASK_QUEUE,
        )
        # подтверждаем отправку
        await message.answer("💭 Сообщение отправлено ИИ, ожидайте ответ...")
