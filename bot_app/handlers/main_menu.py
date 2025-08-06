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

# FSM-состояния для генерации заданий
class GenerateTasksFSM(StatesGroup):
    prompt = State()

# FSM-состояния для проверки ДЗ
class CheckHomeworkFSM(StatesGroup):
    text = State()

# FSM-состояния для чата с GPT
class ChatGPTFSM(StatesGroup):
    message = State()

# --- Генерация заданий ---
@router.callback_query(F.data == "generate_tasks")
async def cb_generate_tasks(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)
    
    await state.set_state(GenerateTasksFSM.prompt)
    await callback.message.edit_text(
        "📚 **Генерация заданий**\n\n"
        "Введите описание заданий, которые нужно сгенерировать.\n"
        "Например: «Задания по алгебре для 8 класса на тему квадратные уравнения»",
        reply_markup=back_button("← Отмена", "back:main")
    )
    await callback.answer()

@router.message(GenerateTasksFSM.prompt)
async def process_generate_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    prompt = message.text.strip()
    if not prompt:
        return await message.answer("❌ Описание не может быть пустым. Введите описание заданий:")
    
    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": None,  # Общая генерация без привязки к ученику
        "prompt": prompt,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()

# --- Проверка ДЗ ---
@router.callback_query(F.data == "check_homework")
async def cb_check_homework(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)
    
    await state.set_state(CheckHomeworkFSM.text)
    await callback.message.edit_text(
        "📝 **Проверка домашнего задания**\n\n"
        "Пришлите фото, PDF или текст домашней работы.\n"
        "Бот проверит её и даст рекомендации в PDF формате.",
        reply_markup=back_button("← Отмена", "back:main")
    )
    await callback.answer()

@router.message(CheckHomeworkFSM.text)
async def process_check_homework(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    text = message.text.strip()
    if not text:
        return await message.answer("❌ Текст не может быть пустым. Введите домашнее задание:")
    
    task = {
        "type": "check_homework",
        "user_id": message.from_user.id,
        "student_id": None,  # Общая проверка без привязки к ученику
        "text": text,
    }
    await _send_task(task)
    await message.answer("🕔 Проверяю ДЗ, ожидайте PDF…")
    await state.clear()

# --- Чат с GPT ---
@router.callback_query(F.data == "chat_gpt")
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)
    
    await state.set_state(ChatGPTFSM.message)
    await callback.message.edit_text(
        "💬 **Чат с GPT**\n\n"
        "Напишите любой вопрос — бот ответит вам прямо в чат.\n"
        "История переписки сохраняется.",
        reply_markup=back_button("← Отмена", "back:main")
    )
    await callback.answer()

@router.message(ChatGPTFSM.message)
async def process_chat_gpt(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    user_message = message.text.strip()
    if not user_message:
        return await message.answer("❌ Сообщение не может быть пустым. Введите ваш вопрос:")
    
    task = {
        "type": "chat",
        "user_id": message.from_user.id,
        "student_id": None,  # Общий чат без привязки к ученику
        "message": user_message,
    }
    await _send_task(task)
    await message.answer("🤖 Обрабатываю ваш вопрос...")
    await state.clear()

# --- Обработка текстовых команд из reply-меню ---
@router.message(F.text == "📚 Генерировать задания")
async def msg_generate_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")
    
    await state.set_state(GenerateTasksFSM.prompt)
    await message.answer(
        "📚 **Генерация заданий**\n\n"
        "Введите описание заданий, которые нужно сгенерировать.\n"
        "Например: «Задания по алгебре для 8 класса на тему квадратные уравнения»",
        reply_markup=back_button("← Отмена", "back:main")
    )

@router.message(F.text == "📝 Проверить ДЗ")
async def msg_check_homework(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")
    
    await state.set_state(CheckHomeworkFSM.text)
    await message.answer(
        "📝 **Проверка домашнего задания**\n\n"
        "Пришлите фото, PDF или текст домашней работы.\n"
        "Бот проверит её и даст рекомендации в PDF формате.",
        reply_markup=back_button("← Отмена", "back:main")
    )

@router.message(F.text == "💬 Чат с GPT")
async def msg_chat_gpt(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")
    
    await state.set_state(ChatGPTFSM.message)
    await message.answer(
        "💬 **Чат с GPT**\n\n"
        "Напишите любой вопрос — бот ответит вам прямо в чат.\n"
        "История переписки сохраняется.",
        reply_markup=back_button("← Отмена", "back:main")
    )

# --- Обработка фото и документов для генерации и проверки ---
@router.message(F.photo)
async def photo_to_generate(message: Message, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.photo[-1].file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,  # Общая обработка без привязки к ученику
        "file_data": b64,
        "file_name": "photo.jpg",
        "prompt": caption,
    }
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")

@router.message(F.document)
async def doc_to_generate(message: Message, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    name = message.document.file_name or "file.pdf"

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,  # Общая обработка без привязки к ученику
        "file_data": b64,
        "file_name": name,
        "prompt": caption,
    }
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…") 