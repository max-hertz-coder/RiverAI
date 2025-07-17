# bot_app/handlers/chatgpt.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import json
import aio_pika

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb
import bot_app.main as main_module  # <— импортируем модуль, а не переменную

router = Router()


class ChatGPTDialog(StatesGroup):
    active = State()


@router.callback_query(F.data.startswith("chat_gpt:"))
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=student_id)
    await state.set_state(ChatGPTDialog.active)
    await callback.message.edit_text(
        "💬 Чат с GPT открыт. Напишите сообщение для ИИ (или /back для выхода):"
    )


@router.message(ChatGPTDialog.active)
async def handle_gpt_dialog_message(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id    = message.from_user.id
    user_text  = message.text.strip()

    # Если выходим из чата
    if user_text.lower() in ("/exit", "/back"):
        task = {
            "type":       "end_chat",
            "user_id":    user_id,
            "student_id": student_id,
        }
        # обращаемся к main_module.rabbit_channel (уже инициализированному в on_startup)
        await main_module.rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode("utf-8")),
            routing_key=config.RABBITMQ_TASK_QUEUE,
        )
        await state.clear()
        await message.answer(
            "🔚 Чат с GPT завершён.",
            reply_markup=chat_menu_kb(student_id, lang="RU"),
        )

    else:
        # обычный запрос к GPT
        task = {
            "type":       "chat_gpt",
            "user_id":    user_id,
            "student_id": student_id,
            "message":    user_text,
        }
        await main_module.rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode("utf-8")),
            routing_key=config.RABBITMQ_TASK_QUEUE,
        )
        await message.answer("💭 Сообщение отправлено ИИ, ожидайте ответ...")
