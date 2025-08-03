import json
import logging
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


# FSM-состояния для чата с GPT
class ChatGPTFSM(StatesGroup):
    message = State()


# --- Обработчик кнопки "Чат с GPT" ---
@router.callback_query(F.data.startswith("chat_gpt:"))
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)

    student_id = int(callback.data.split(":", 1)[1])
    await state.set_state(ChatGPTFSM.message)
    await state.update_data(student_id=student_id)
    
    await callback.message.edit_text(
        "💬 **Режим чата с GPT**\n\n"
        "Напишите любой вопрос — бот ответит вам прямо в чат.\n"
        "История переписки сохраняется для каждого ученика.",
        reply_markup=back_button("← Назад", f"student:{student_id}")
    )


# --- Обработка сообщений для чата с GPT ---
@router.message(ChatGPTFSM.message)
async def chat_message(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    student_id = data.get("student_id")
    user_message = message.text.strip()

    if not user_message:
        return await message.answer("❌ Сообщение не может быть пустым. Введите ваш вопрос:")

    task = {
        "type": "chat",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "message": user_message,
    }
    await _send_task(task)


# --- Обработка результатов чата с GPT ---
@router.callback_query(F.data.startswith("chat_gpt_result:"))
async def cb_chat_gpt_result(callback: CallbackQuery):
    task_id = callback.data.split(":", 1)[1]
    result = pending_tasks.get(task_id)
    
    if not result:
        return await callback.answer("❌ Результат не найден", show_alert=True)
    
    if result.get("type") == "error":
        await callback.message.edit_text(
            f"❌ Ошибка при обработке чата:\n{result.get('message', 'Неизвестная ошибка')}",
            reply_markup=back_button("← Назад", f"student:{result.get('student_id')}")
        )
        return
    
    # Отправляем ответ GPT
    answer = result.get("answer", "")
    if answer:
        # Ограничиваем длину сообщения
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (ответ обрезан)"
        
        await callback.message.answer(
            answer,
            reply_markup=back_button("← Назад", f"student:{result.get('student_id')}")
        )
    
    # Удаляем исходное сообщение
    await callback.message.delete()


# --- Очистка истории чата ---
@router.callback_query(F.data.startswith("clear_chat:"))
async def cb_clear_chat(callback: CallbackQuery):
    student_id = int(callback.data.split(":", 1)[1])
    
    task = {
        "type": "end_chat",
        "user_id": callback.from_user.id,
        "student_id": student_id,
    }
    await _send_task(task)
    
    await callback.answer("🗑 История чата очищена", show_alert=True) 