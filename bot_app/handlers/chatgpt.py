# bot_app/handlers/chatgpt.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import json
import aio_pika

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb
import bot_app.main as main_module  # модуль, где хранятся rabbit_channel

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

    # Функция-обёртка для публикации в очередь
    async def publish_task(task: dict) -> bool:
        channel = main_module.rabbit_channel
        # если канал ещё не инициализирован — пробуем пересоздать
        if channel is None:
            try:
                conn = await aio_pika.connect_robust(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    login=config.RABBITMQ_USER,
                    password=config.RABBITMQ_PASS,
                )
                channel = await conn.channel()
                main_module.rabbit_channel = channel
            except Exception:
                return False
        # публикуем задачу
        try:
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(task).encode("utf-8")),
                routing_key=config.RABBITMQ_TASK_QUEUE,
            )
            return True
        except Exception:
            return False

    # Если пользователь выходит из чата
    if user_text.lower() in ("/exit", "/back"):
        task = {
            "type":       "end_chat",
            "user_id":    user_id,
            "student_id": student_id,
        }
        ok = await publish_task(task)
        await state.clear()
        if ok:
            await message.answer(
                "🔚 Чат с GPT завершён.",
                reply_markup=chat_menu_kb(student_id, lang="RU"),
            )
        else:
            await message.answer("⚠️ Очередь недоступна. Попробуйте позже.")
        return

    # Иначе — обычный запрос в GPT
    task = {
        "type":       "chat_gpt",
        "user_id":    user_id,
        "student_id": student_id,
        "message":    user_text,
    }
    ok = await publish_task(task)
    if ok:
        await message.answer("💭 Сообщение отправлено ИИ, ожидайте ответ...")
    else:
        await message.answer("⚠️ Не удалось отправить задачу в очередь. Попробуйте позже.")
