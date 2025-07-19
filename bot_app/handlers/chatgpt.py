from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import json
import aio_pika

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb

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
    text       = message.text.strip()

    # Если выходим из чата
    if text.lower() in ("/back", "/exit"):
        task = {
            "type":       "end_chat",
            "user_id":    user_id,
            "student_id": student_id,
        }
    else:
        # Обычный чат-запрос
        task = {
            "type":       "chat_gpt",
            "user_id":    user_id,
            "student_id": student_id,
            "message":    text,
        }

    # Пытаемся опубликовать задачу в очередь
    try:
        connection = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST,
            port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER,
            password=config.RABBITMQ_PASS,
        )
        channel = await connection.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode("utf-8")),
            routing_key=config.TASK_QUEUE,  # убедитесь, что в config это TASK_QUEUE
        )
        await connection.close()

        # Если это завершение чата
        if task["type"] == "end_chat":
            await state.clear()
            await message.answer(
                "🔚 Чат с GPT завершён.",
                reply_markup=chat_menu_kb(student_id),
            )
        else:
            await message.answer(
                "💭 Сообщение отправлено ИИ, ожидайте ответ...",
                reply_markup=chat_menu_kb(student_id),
            )

    except Exception as e:
        # Любая ошибка при публикации — уведомляем пользователя
        await message.answer("⚠️ Не удалось отправить задачу в очередь. Попробуйте позже.")
        # и логируем для себя
        logging.exception("Ошибка публикации задачи в очередь")
