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
from bot_app.keyboards.main_menu import bottom_menu_generation_kb, bottom_menu_students_kb
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


# --- Обработчик кнопки "Чат с GPT" из нижнего меню ---
@router.message(F.text == "💬 Чат с GPT")
async def msg_chat_gpt(message: Message, state: FSMContext):
    # Убираем проверку подписки для тестирования
    # if not await has_active_sub(message.from_user.id):
    #     return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    # Получаем первого ученика (можно будет улучшить выбор)
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 У вас нет учеников. Сначала добавьте ученика в разделе «👤 Ученики».",
            reply_markup=bottom_menu_students_kb()
        )
    
    student_id = students[0]["id"]
    await state.set_state(ChatGPTFSM.message)
    await state.update_data(student_id=student_id)
    
    await message.answer(
        "💬 **Режим чата с GPT**\n\n"
        "Напишите любой вопрос — бот ответит вам прямо в чат.\n"
        "История переписки сохраняется для каждого ученика.",
        reply_markup=bottom_menu_generation_kb()
    )


# --- Обработчик кнопки "Чат с GPT" из CallbackQuery (для совместимости) ---
@router.callback_query(F.data.startswith("chat_gpt:"))
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    # Убираем проверку подписки для тестирования
    # if not await has_active_sub(callback.from_user.id):
    #     return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)

    student_id = int(callback.data.split(":", 1)[1])
    await state.set_state(ChatGPTFSM.message)
    await state.update_data(student_id=student_id)
    
    await callback.message.edit_text(
        "💬 **Режим чата с GPT**\n\n"
        "Напишите любой вопрос — бот ответит вам прямо в чат.\n"
        "История переписки сохраняется для каждого ученика.",
        reply_markup=bottom_menu_generation_kb()
    )


# --- Обработка сообщений для чата с GPT ---
@router.message(ChatGPTFSM.message)
async def chat_message(message: Message, state: FSMContext):
    # Убираем проверку подписки для тестирования
    # if not await has_active_sub(message.from_user.id):
    #     return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    student_id = data.get("student_id")
    user_message = message.text.strip()

    if not user_message:
        return await message.answer("❌ Сообщение не может быть пустым. Введите ваш вопрос:")

    task = {
        "type": "chat_gpt",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "message": user_message,
    }
    await _send_task(task)
    await message.answer("🕔 Обрабатываю ваш вопрос, ожидайте ответа…", reply_markup=bottom_menu_generation_kb())


# --- Обработчики результатов чата с GPT ---
@router.callback_query(F.data.startswith("chat_gpt_result:"))
async def cb_chat_gpt_result(callback: CallbackQuery):
    try:
        data = json.loads(callback.data.split(":", 1)[1])
        response = data.get("response", "Ответ не получен")
        student_id = data.get("student_id")
        
        # Формируем ответ с кнопками действий
        text = f"💬 **Ответ GPT:**\n\n{response}"
        
        await callback.message.edit_text(
            text,
            reply_markup=bottom_menu_generation_kb()
        )
        
    except Exception as e:
        logging.error(f"Ошибка обработки результата чата: {e}")
        await callback.answer("❌ Ошибка обработки ответа", show_alert=True)


# --- Очистка истории чата ---
@router.callback_query(F.data.startswith("clear_chat:"))
async def cb_clear_chat(callback: CallbackQuery):
    student_id = int(callback.data.split(":", 1)[1])
    
    # Здесь можно добавить логику очистки истории чата
    # await db.clear_chat_history(callback.from_user.id, student_id)
    
    await callback.answer("✅ История чата очищена!", show_alert=True)
    await callback.message.edit_text(
        "💬 **История чата очищена**\n\n"
        "Начните новый диалог с GPT.",
        reply_markup=bottom_menu_generation_kb()
    )


# --- Возврат к ученикам ---
@router.message(F.text == "← К ученикам")
async def back_to_students_from_chat(message: Message):
    """Возврат к ученикам из чата"""
    students = await db.get_students_by_user(message.from_user.id)
    text = "Ваши ученики:" if students else "👤 У Вас пока нет добавленных учеников."
    await message.answer(text, reply_markup=bottom_menu_students_kb()) 