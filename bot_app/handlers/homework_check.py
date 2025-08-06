import json
import base64
import logging
from io import BytesIO
from datetime import datetime

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
from bot_app.rabbit import pending_tasks
from bot_app.keyboards.main_menu import back_button
from bot_app.database import db
from bot_app.utils.task_utils import create_task_with_context

router = Router()


# --- Проверка подписки ---
async def has_active_sub(user_id: int) -> bool:
    user = await db.get_user_by_tg_id(user_id)
    if not user:
        return False
    expiry = user.get("subscription_expires")
    if not expiry:
        return False
    return datetime.fromisoformat(str(expiry)) > datetime.now()


# --- Отправка задачи ---
async def _send_task(task: dict):
    try:
        # Создаем задачу с контекстом
        task_with_context = await create_task_with_context(task)
        
        if rabbit_channel:
            await rabbit_channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(task_with_context).encode()),
                routing_key=config.TASK_QUEUE
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
                aio_pika.Message(body=json.dumps(task_with_context).encode()),
                routing_key=config.TASK_QUEUE
            )
            await conn.close()
    except Exception:
        logging.exception("Ошибка отправки задачи в очередь")


# FSM-состояния для проверки ДЗ
class HomeworkCheckFSM(StatesGroup):
    text = State()


# --- Обработчик кнопки "Проверка ДЗ" (для учеников) ---
@router.callback_query(F.data.startswith("check_homework:"))
async def cb_check_homework(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)

    student_id = int(callback.data.split(":", 1)[1])
    await state.set_state(HomeworkCheckFSM.text)
    await state.update_data(student_id=student_id)
    
    await callback.message.edit_text(
        "✅ **Режим проверки ДЗ**\n\n"
        "Пришлите фото, PDF или текст домашней работы.\n"
        "Бот проверит её и даст рекомендации в PDF формате.",
        reply_markup=back_button("← Назад", f"student:{student_id}")
    )


# --- Обработка текста для проверки ДЗ ---
@router.message(HomeworkCheckFSM.text)
async def text_to_check(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    student_id = data.get("student_id")
    text = message.text.strip()

    if not text:
        return await message.answer("❌ Текст не может быть пустым. Введите домашнее задание:")

    task = {
        "type": "check_homework",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "text": text,
    }
    await _send_task(task)
    await state.clear()
    await message.answer("🕔 Проверяю ДЗ, ожидайте PDF…")


# --- Обработка результатов проверки ДЗ ---
@router.callback_query(F.data.startswith("check_homework_result:"))
async def cb_check_homework_result(callback: CallbackQuery):
    task_id = callback.data.split(":", 1)[1]
    result = pending_tasks.get(task_id)
    
    if not result:
        return await callback.answer("❌ Результат не найден", show_alert=True)
    
    if result.get("type") == "error":
        await callback.message.edit_text(
            f"❌ Ошибка при проверке ДЗ:\n{result.get('message', 'Неизвестная ошибка')}",
            reply_markup=back_button("← Назад", f"student:{result.get('student_id')}")
        )
        return
    
    # Отправляем PDF, если есть
    if result.get("pdf_path"):
        try:
            from aiogram.types import FSInputFile
            await callback.message.answer_document(
                FSInputFile(result["pdf_path"]),
                caption="📄 Результат проверки ДЗ"
            )
        except Exception as e:
            logging.exception("Ошибка отправки PDF: %s", e)
    
    # Отправляем текстовый отчет
    report_text = result.get("report_text", "")
    if report_text:
        # Ограничиваем длину сообщения
        if len(report_text) > 4000:
            report_text = report_text[:4000] + "\n\n... (отчет обрезан)"
        
        await callback.message.answer(
            f"📋 **Результат проверки ДЗ:**\n\n{report_text}",
            reply_markup=back_button("← Назад", f"student:{result.get('student_id')}")
        )
    
    # Удаляем исходное сообщение
    await callback.message.delete() 