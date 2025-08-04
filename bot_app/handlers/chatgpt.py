import logging
import json
import aio_pika

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
from bot_app.keyboards.chat_menu import chat_menu_kb
from bot_app.utils.task_utils import create_task_with_context

router = Router()
logger = logging.getLogger(__name__)


class ChatState(StatesGroup):
    active = State()


@router.callback_query(F.data.startswith("chat:"))
async def cb_chat_start(query: CallbackQuery, state: FSMContext):
    try:
        sid = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await query.answer("❌ Ошибка: неверный формат ID", show_alert=True)

    await state.update_data(student_id=sid)
    await state.set_state(ChatState.active)
    await query.message.edit_text("💬 Напишите сообщение ИИ (или /back):")


@router.message(ChatState.active)
async def cb_chat_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    sid = data.get("student_id")
    txt = message.text.strip()

    if not txt:
        return await message.answer("❌ Пустое сообщение. Введите текст.")

    logger.info(f"📨 Сообщение в чат: user_id={message.from_user.id}, student_id={sid}, length={len(txt)}")

    ttype = "end_chat" if txt.lower() in ("/back", "/exit") else "chat"

    task = {
        "type": ttype,
        "user_id": message.from_user.id,
        "student_id": sid,
        "message": txt
    }

    try:
        logger.info("🔄 Создание задачи с контекстом...")
        task_with_context = await create_task_with_context(task)
        task_id = task_with_context.get("task_id")
        message_body = json.dumps(task_with_context).encode("utf-8")

        logger.info(f"📦 Задача создана: task_id={task_id}")
        logger.debug(f"📄 Содержимое задачи: {task_with_context}")

        if rabbit_channel:
            logger.info("📡 Используется активный RabbitMQ канал")
            await rabbit_channel.default_exchange.publish(
                aio_pika.Message(body=message_body),
                routing_key=config.TASK_QUEUE
            )
        else:
            logger.warning("📡 Отсутствует общий канал, создаётся новое соединение...")
            conn = await aio_pika.connect_robust(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                login=config.RABBITMQ_USER,
                password=config.RABBITMQ_PASS,
            )
            ch = await conn.channel()
            await ch.default_exchange.publish(
                aio_pika.Message(body=message_body),
                routing_key=config.TASK_QUEUE
            )
            await conn.close()

        logger.info(f"✅ Задача отправлена: task_id={task_id}")

    except Exception as e:
        logger.exception("❌ Ошибка при отправке в очередь")
        return await message.answer("⚠️ Ошибка при отправке задачи. Попробуйте позже.")

    if ttype == "end_chat":
        await state.clear()
        await message.answer("🔚 Чат завершён", reply_markup=chat_menu_kb(sid))
