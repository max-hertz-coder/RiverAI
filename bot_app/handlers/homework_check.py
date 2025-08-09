import json
import logging
from datetime import datetime

import aio_pika
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
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


class HomeworkCheckFSM(StatesGroup):
    text = State()


@router.callback_query(F.data.startswith("check_homework:"))
async def cb_check_homework(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.",
            show_alert=True,
        )

    try:
        student_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("❌ Неверный формат ID", show_alert=True)

    await state.set_state(HomeworkCheckFSM.text)
    await state.update_data(student_id=student_id)

    await callback.message.edit_text(
        "✅ **Режим проверки ДЗ**\n\n"
        "Пришлите текст, фото или PDF домашней работы.\n"
        "Текст пришлите прямо сюда; фото/PDF — просто отправьте файлом/фото.",
        reply_markup=back_button("← Назад", f"student:{student_id}"),
    )
    await callback.answer()


@router.message(HomeworkCheckFSM.text)
async def text_to_check(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    data = await state.get_data()
    student_id = data.get("student_id")
    text = (message.text or "").strip()

    if not text:
        return await message.answer("❌ Текст не может быть пустым. Введите домашнее задание:")

    task = {
        "type": "check_homework",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "text": text,
    }

    try:
        await _send_task(task)
    except Exception:
        return await message.answer("⚠️ Не удалось запустить проверку. Попробуйте ещё раз.")

    await state.clear()
    await message.answer("🕔 Проверяю ДЗ, ожидайте PDF…")
    # Результат придёт через result_consumer напрямую пользователю.
