# bot_app/handlers/homework_check.py
import json
import logging
from datetime import datetime

import aio_pika
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config
from bot_app.keyboards.chat_menu import back_button
from bot_app.database import db
from bot_app.utils.task_utils import create_task_with_context
from bot_app import rabbit  # publish_task

router = Router()
logger = logging.getLogger(__name__)


# ---------- helpers ----------

async def _has_active_sub(user_id: int) -> bool:
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
    """
    Публикуем задачу в очередь. Сначала пробуем наш общий publish_task,
    при недоступности — создаём соединение напрямую.
    """
    try:
        task_with_context = await create_task_with_context(task)
        await rabbit.publish_task(task_with_context)
        return
    except Exception:
        logger.warning("publish_task fallback to raw AMQP")

    # Fallback публикация напрямую (редкий случай)
    body = json.dumps(task).encode("utf-8")
    conn = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    try:
        ch = await conn.channel()
        await ch.default_exchange.publish(aio_pika.Message(body=body), routing_key=config.TASK_QUEUE)
    finally:
        await conn.close()


# ---------- FSM: ввод текста для проверки ----------

class HomeworkCheckFSM(StatesGroup):
    text = State()


@router.callback_query(F.data.startswith("check_homework:"))
async def cb_check_homework(callback: CallbackQuery, state: FSMContext):
    if not await _has_active_sub(callback.from_user.id):
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
    if not await _has_active_sub(message.from_user.id):
        return await message.answer(
            "❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ."
        )

    data = await state.get_data()
    student_id = data.get("student_id")

    # 1) Текст — отправляем задачу check_homework
    if message.text:
        text = message.text.strip()
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
        return await message.answer("🕔 Проверяю ДЗ, ожидайте PDF…")

    # 2) Фото / документ — прокидываем в ocr_and_check (воркер сам сделает OCR)
    if message.photo:
        file_id = message.photo[-1].file_id
        task = {
            "type": "ocr_and_check",
            "user_id": message.from_user.id,
            "student_id": student_id,
            "file_id": file_id,
            "file_kind": "photo",
        }
        try:
            await _send_task(task)
        except Exception:
            return await message.answer("⚠️ Не удалось запустить распознавание. Попробуйте ещё раз.")
        await state.clear()
        return await message.answer("🕔 Распознаю и проверяю ДЗ, ожидайте PDF…")

    if message.document:
        file_id = message.document.file_id
        mime = (message.document.mime_type or "").lower()
        task = {
            "type": "ocr_and_check",
            "user_id": message.from_user.id,
            "student_id": student_id,
            "file_id": file_id,
            "file_kind": "document",
            "mime": mime,
        }
        try:
            await _send_task(task)
        except Exception:
            return await message.answer("⚠️ Не удалось запустить распознавание. Попробуйте ещё раз.")
        await state.clear()
        return await message.answer("🕔 Распознаю и проверяю ДЗ, ожидайте PDF…")

    return await message.answer("❌ Отправьте текст, фото или PDF.")


# ---------- «✏️ Исправить проверку» ----------

class RefineCheck(StatesGroup):
    waiting_text = State()


@router.callback_query(F.data.startswith("refine_check:"))
async def on_refine_check(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(RefineCheck.waiting_text)
    await cb.message.answer(
        "✏️ Напишите, что нужно исправить/уточнить в проверке.\n"
        "Отправьте одним сообщением.",
        reply_markup=back_button("← Назад", "back:main"),
    )


@router.message(RefineCheck.waiting_text)
async def on_refine_text(msg: Message, state: FSMContext):
    refine_text = (msg.text or "").strip()
    await state.clear()

    task = {
        "type": "check_homework",
        "user_id": msg.from_user.id,
        "text": refine_text,     # уточнение берём как новый текст к проверке
        "refine": refine_text,   # дополнительно прокинем как «правки»
    }
    task_with_ctx = await create_task_with_context(task)
    await rabbit.publish_task(task_with_ctx)

    await msg.answer("🕔 Повторно проверяю ДЗ с учётом ваших правок…")
