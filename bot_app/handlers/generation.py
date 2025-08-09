import json
import base64
import logging
from datetime import datetime
from io import BytesIO

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


class TasksFSM(StatesGroup):
    desc = State()


class RefineTasksFSM(StatesGroup):
    notes = State()


# ВНИМАНИЕ: обработку F.photo/F.document вынес в ocr_and_generate.py,
# чтобы исключить дублирование и двойные триггеры.


@router.callback_query(F.data.startswith("generate_tasks:"))
async def cb_tasks(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True
        )

    try:
        sid = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return await callback.answer("❌ Неверный формат запроса", show_alert=True)

    await state.update_data(student_id=sid)
    await state.set_state(TasksFSM.desc)
    await callback.message.edit_text(
        "Введите текстовый запрос для генерации заданий:",
        reply_markup=back_button("← Отмена", "back:chat"),
    )
    await callback.answer()


@router.message(TasksFSM.desc)
async def proc_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    data = await state.get_data()
    prompt = (message.text or "").strip()
    if not prompt:
        return await message.answer("❌ Пустой запрос. Введите текст для генерации.")

    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": data.get("student_id"),
        "prompt": prompt,
    }

    try:
        await _send_task(task)
    except Exception:
        await message.answer("⚠️ Не удалось запустить генерацию. Попробуйте ещё раз.")
        return

    await message.answer("🕔 Генерируются задания, ожидайте…")
    await state.clear()


# ——— Refine (исправить) ———
# По ТЗ: исправление работает через повторную отправку Solutions.pdf + текст-промпт.
@router.callback_query(F.data == "refine_tasks")
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RefineTasksFSM.notes)
    await callback.message.edit_text(
        "✏️ Ответьте на сообщение с **Solutions.pdf** и опишите, как изменить задания.\n"
        "Бот перезапустит генерацию по вашему промпту.",
        reply_markup=back_button("← Отмена", "back:main"),
    )
    await callback.answer()


@router.message(RefineTasksFSM.notes)
async def proc_refine_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    user_prompt = (message.text or "").strip()
    if not user_prompt:
        return await message.answer("❌ Пустой запрос. Опишите правки к заданиям.")

    # Требуем, чтобы это был ответ на Solutions.pdf
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer("📎 Пожалуйста, отправьте ваш текст **в ответ** на сообщение с Solutions.pdf.")

    doc = message.reply_to_message.document
    file_name = doc.file_name or "Solutions.pdf"

    bio = BytesIO()
    await message.bot.download(doc.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    # Явно просим сгенерировать только задания
    final_prompt = f"Сгенерируйте ТОЛЬКО задания без решений и ответов. {user_prompt}"

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,  # исправление без привязки к ученику
        "file_data": b64,
        "file_name": file_name,
        "prompt": final_prompt,
        "refine": True,
    }

    try:
        await _send_task(task)
    except Exception:
        await message.answer("⚠️ Не удалось запустить переделку. Попробуйте позже.")
        return

    await message.answer("📝 Переделываю задания по вашим инструкциям…")
    await state.clear()


@router.callback_query(F.data == "tasks_ok")
async def cb_tasks_ok(callback: CallbackQuery):
    logger.info("tasks_ok от пользователя %s", callback.from_user.id)
    await callback.answer("👍 Отлично!")
    try:
        await callback.message.edit_text("🎉 Супер! Если понадобится что-то ещё — пишите.")
    except Exception:
        # Сообщение могло быть уже отредактировано/удалено пользователем
        pass
