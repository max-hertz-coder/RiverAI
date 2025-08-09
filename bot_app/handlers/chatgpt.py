import json
import logging
from datetime import datetime

import aio_pika
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
from bot_app.keyboards.chat_menu import chat_menu_kb
from bot_app.keyboards.main_menu import back_button
from bot_app.database import db
from bot_app.utils.task_utils import create_task_with_context

router = Router()
logger = logging.getLogger(__name__)


async def has_active_sub(user_id: int) -> bool:
    user = await db.get_user_by_tg_id(user_id)
    if not user:
        return False
    expiry = user.get("subscription_expires")
    if not expiry:
        return False
    try:
        return datetime.fromisoformat(str(expiry)) > datetime.now()
    except Exception:
        return False


async def _send_task(task: dict):
    """Единая отправка задачи в RabbitMQ с обогащением контекстом."""
    try:
        task_with_context = await create_task_with_context(task)
        body = json.dumps(task_with_context).encode("utf-8")

        if rabbit_channel:
            await rabbit_channel.default_exchange.publish(
                aio_pika.Message(body=body),
                routing_key=config.TASK_QUEUE,
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
                aio_pika.Message(body=body),
                routing_key=config.TASK_QUEUE,
            )
            await conn.close()
    except Exception as e:
        logger.exception("Ошибка отправки задачи в очередь: %s", e)
        raise


class ChatState(StatesGroup):
    active = State()


# Поддержим оба варианта callback-данных: chat_gpt:<sid> и chat:<sid>
@router.callback_query(F.data.startswith("chat_gpt:"))
@router.callback_query(F.data.startswith("chat:"))
async def cb_chat_start(query: CallbackQuery, state: FSMContext):
    if not await has_active_sub(query.from_user.id):
        return await query.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.",
            show_alert=True,
        )

    try:
        sid = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await query.answer("❌ Ошибка: неверный формат ID", show_alert=True)

    await state.update_data(student_id=sid)
    await state.set_state(ChatState.active)
    await query.message.edit_text(
        "💬 Напишите сообщение для ИИ.\n"
        "Команда /back — завершить чат.",
        reply_markup=back_button("← Назад", "back:main"),
    )
    await query.answer()


@router.message(ChatState.active)
async def cb_chat_msg(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    data = await state.get_data()
    sid = data.get("student_id")
    txt = (message.text or "").strip()

    if not txt:
        return await message.answer("❌ Пустое сообщение. Введите текст.")

    # /back — завершение чата
    ttype = "end_chat" if txt.lower() in ("/back", "/exit") else "chat"

    task = {
        "type": ttype,
        "user_id": message.from_user.id,
        "student_id": sid,
        "message": txt,
    }

    try:
        await _send_task(task)
    except Exception:
        await message.answer(
            "⚠️ Ошибка при отправке задачи. Попробуйте позже.",
            reply_markup=back_button("← Назад", "back:main"),
        )
        return

    if ttype == "end_chat":
        await state.clear()
        await message.answer("🔚 Чат завершён", reply_markup=chat_menu_kb(sid))
    else:
        # Для чата ответы приходят через result_consumer → пользователю в чат
        await message.answer("🕔 Пишу ответ…", reply_markup=back_button("← Назад", "back:main"))


# Явная очистка истории / завершение (кнопкой)
@router.callback_query(F.data.startswith("clear_chat:"))
async def cb_clear_chat(callback: CallbackQuery, state: FSMContext):
    try:
        student_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("Ошибка при очистке чата", show_alert=True)

    task = {
        "type": "end_chat",
        "user_id": callback.from_user.id,
        "student_id": student_id,
    }
    try:
        await _send_task(task)
    except Exception:
        await callback.answer("⚠️ Не удалось завершить чат", show_alert=True)
        return

    await state.clear()
    await callback.answer("🗑 История чата очищена", show_alert=True)
    await callback.message.edit_text("🔚 Чат завершён", reply_markup=chat_menu_kb(student_id))
