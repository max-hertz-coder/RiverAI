import logging
import json
import aio_pika

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb

router = Router()
logger = logging.getLogger(__name__)

class ChatGPTDialog(StatesGroup):
    active = State()

@router.callback_query(F.data.startswith("chat_gpt:"))
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":",1)[1])
    await state.update_data(student_id=student_id)
    await state.set_state(ChatGPTDialog.active)
    await callback.message.edit_text("💬 Чат с GPT открыт. Введите сообщение для ИИ (или /back):")

@router.message(ChatGPTDialog.active)
async def handle_gpt(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data["student_id"]
    user_id = message.from_user.id
    text = message.text.strip()

    if text.lower() in ("/back","/exit"):
        task = {"type":"end_chat","user_id":user_id,"student_id":student_id}
        clear = True
    else:
        task = {"type":"chat","user_id":user_id,"student_id":student_id,"message":text}
        clear = False

    try:
        conn = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER, password=config.RABBITMQ_PASS
        )
        ch = await conn.channel()
        await ch.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode()),
            routing_key=config.TASK_QUEUE
        )
        await conn.close()
    except Exception:
        logger.exception("Ошибка публикации в очередь chat_gpt")
        return await message.answer("⚠️ Не удалось отправить сообщение ИИ. Попробуйте позже.")

    if clear:
        await state.clear()
        await message.answer("🔚 Чат завершён.", reply_markup=chat_menu_kb(student_id, lang="RU"))
    else:
        await message.answer("💭 Сообщение отправлено ИИ, ожидайте ответ...", reply_markup=chat_menu_kb(student_id, lang="RU"))
