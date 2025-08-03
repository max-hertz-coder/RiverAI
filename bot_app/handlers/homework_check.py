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


# FSM-состояния для проверки ДЗ
class HomeworkCheckFSM(StatesGroup):
    text = State()


# --- Обработчик кнопки "Проверка ДЗ" из нижнего меню ---
@router.message(F.text == "✅ Проверить ДЗ")
async def msg_check_homework(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    # Получаем первого ученика (можно будет улучшить выбор)
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 У вас нет учеников. Сначала добавьте ученика в разделе «👤 Ученики».",
            reply_markup=bottom_menu_students_kb()
        )
    
    student_id = students[0]["id"]
    await state.set_state(HomeworkCheckFSM.text)
    await state.update_data(student_id=student_id)
    
    await message.answer(
        "✅ **Режим проверки ДЗ**\n\n"
        "Пришлите фото, PDF или текст домашней работы.\n"
        "Бот проверит её и даст рекомендации в PDF формате.",
        reply_markup=bottom_menu_generation_kb()
    )


# --- Обработчик кнопки "Проверка ДЗ" из CallbackQuery (для совместимости) ---
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
        reply_markup=bottom_menu_generation_kb()
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
    await message.answer("🕔 Проверяю домашнее задание, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())


# --- Обработка фото для проверки ДЗ ---
@router.message(HomeworkCheckFSM.text, F.photo)
async def photo_to_check(message: Message, state: FSMContext, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    student_id = data.get("student_id")
    caption = (message.caption or "").strip()
    
    bio = BytesIO()
    await bot.download(message.photo[-1].file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    task = {
        "type": "check_homework",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "file_data": b64,
        "file_name": "homework_photo.jpg",
        "prompt": caption,
    }
    await _send_task(task)
    await state.clear()
    await message.answer("🕔 Проверяю домашнее задание, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())


# --- Обработка документа для проверки ДЗ ---
@router.message(HomeworkCheckFSM.text, F.document)
async def document_to_check(message: Message, state: FSMContext, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    student_id = data.get("student_id")
    caption = (message.caption or "").strip()
    
    bio = BytesIO()
    await bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    task = {
        "type": "check_homework",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "file_data": b64,
        "file_name": message.document.file_name,
        "prompt": caption,
    }
    await _send_task(task)
    await state.clear()
    await message.answer("🕔 Проверяю домашнее задание, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())


# --- Обработчики результатов проверки ДЗ ---
@router.callback_query(F.data.startswith("check_homework_result:"))
async def cb_check_homework_result(callback: CallbackQuery):
    try:
        data = json.loads(callback.data.split(":", 1)[1])
        result = data.get("result", "Результат не получен")
        student_id = data.get("student_id")
        
        # Формируем ответ с кнопками действий
        text = f"✅ **Результат проверки ДЗ:**\n\n{result}"
        
        await callback.message.edit_text(
            text,
            reply_markup=bottom_menu_generation_kb()
        )
        
    except Exception as e:
        logging.error(f"Ошибка обработки результата проверки ДЗ: {e}")
        await callback.answer("❌ Ошибка обработки результата", show_alert=True)


# --- Возврат к ученикам ---
@router.message(F.text == "← К ученикам")
async def back_to_students_from_homework(message: Message):
    """Возврат к ученикам из проверки ДЗ"""
    students = await db.get_students_by_user(message.from_user.id)
    text = "Ваши ученики:" if students else "👤 У Вас пока нет добавленных учеников."
    await message.answer(text, reply_markup=bottom_menu_students_kb()) 