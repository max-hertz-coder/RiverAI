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


# FSM-состояния
class TasksFSM(StatesGroup):
    desc = State()

class RefineTasksFSM(StatesGroup):
    notes = State()


# --- Генерация из фото ---
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
        "student_id": None,
        "file_data": b64,
        "file_name": "photo.jpg",
        "prompt": caption,
    }
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")


# --- Генерация из документа ---
@router.message(F.document)
async def doc_to_generate(message: Message, bot: Bot):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    caption = (message.caption or "").strip()
    bio = BytesIO()
    await bot.download(message.document.file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()

    task = {
        "type": "ocr_and_generate",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": message.document.file_name,
        "prompt": caption,
    }
    await _send_task(task)
    await message.answer("🕔 Распознаю и генерирую задания, ожидайте PDF…")


# --- Генерация заданий через нижнее меню ---
@router.message(F.text == "📝 Задания")
async def msg_generate_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    # Показываем список учеников для выбора
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 У вас нет учеников. Сначала добавьте ученика в разделе «👤 Ученики».",
            reply_markup=bottom_menu_students_kb()
        )
    
    await state.set_state(TasksFSM.desc)
    await message.answer(
        "📝 **Генерация заданий**\n\n"
        "Опишите, какие задания нужно сгенерировать:\n"
        "• Тема или раздел\n"
        "• Тип заданий (тесты, задачи, упражнения)\n"
        "• Уровень сложности\n"
        "• Количество заданий",
        reply_markup=bottom_menu_generation_kb()
    )


# --- Обработка описания для генерации заданий ---
@router.message(TasksFSM.desc)
async def proc_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    desc = message.text.strip()
    if not desc:
        return await message.answer("❌ Описание не может быть пустым. Введите описание заданий:")

    # Получаем первого ученика (можно будет улучшить выбор)
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer("👤 У вас нет учеников. Сначала добавьте ученика.")
    
    student_id = students[0]["id"]

    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "description": desc,
    }
    await _send_task(task)
    await state.clear()
    await message.answer("🕔 Генерирую задания, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())


# --- Генерация учебного плана через нижнее меню ---
@router.message(F.text == "📄 Учебный план")
async def msg_generate_plan(message: Message, state: FSMContext):
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
    student = await db.get_student_by_id(student_id)

    task = {
        "type": "generate_plan",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "description": f"Учебный план для ученика {student['name']} по предмету {student['subject']}",
    }
    await _send_task(task)
    await message.answer("🕔 Генерирую учебный план, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())


# --- Обработчики для совместимости с callback ---
@router.callback_query(F.data.startswith("generate_tasks:"))
async def cb_tasks(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)

    student_id = int(callback.data.split(":", 1)[1])
    await state.set_state(TasksFSM.desc)
    await state.update_data(student_id=student_id)
    await callback.message.edit_text(
        "📝 **Генерация заданий**\n\n"
        "Опишите, какие задания нужно сгенерировать:\n"
        "• Тема или раздел\n"
        "• Тип заданий (тесты, задачи, упражнения)\n"
        "• Уровень сложности\n"
        "• Количество заданий",
        reply_markup=bottom_menu_generation_kb()
    )


@router.callback_query(F.data.startswith("refine_tasks:"))
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    if not await has_active_sub(callback.from_user.id):
        return await callback.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.", show_alert=True)

    student_id = int(callback.data.split(":", 1)[1])
    await state.set_state(RefineTasksFSM.notes)
    await state.update_data(student_id=student_id)
    await callback.message.edit_text(
        "✏️ **Исправление заданий**\n\n"
        "Опишите, что нужно изменить в заданиях:",
        reply_markup=bottom_menu_generation_kb()
    )


@router.message(RefineTasksFSM.notes)
async def proc_refine_tasks(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ У вас нет активной подписки. Перейдите в 💳 Подписка и оформите доступ.")

    data = await state.get_data()
    student_id = data.get("student_id")
    notes = message.text.strip()

    if not notes:
        return await message.answer("❌ Описание изменений не может быть пустым. Введите, что нужно изменить:")

    task = {
        "type": "refine_tasks",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "notes": notes,
    }
    await _send_task(task)
    await state.clear()
    await message.answer("🕔 Исправляю задания, ожидайте PDF…", reply_markup=bottom_menu_generation_kb())


# --- Обработчики результатов ---
@router.callback_query(F.data == "tasks_ok")
async def cb_tasks_ok(callback: CallbackQuery):
    await callback.answer("✅ Задания сохранены!", show_alert=True)


@router.callback_query(F.data == "back:chat")
async def cb_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "👤 Выберите действие:",
        reply_markup=bottom_menu_students_kb()
    )


# --- Возврат к ученикам ---
@router.message(F.text == "← К ученикам")
async def back_to_students_from_generation(message: Message):
    """Возврат к ученикам из генерации"""
    students = await db.get_students_by_user(message.from_user.id)
    text = "Ваши ученики:" if students else "👤 У Вас пока нет добавленных учеников."
    await message.answer(text, reply_markup=bottom_menu_students_kb())

# --- Обработчики для английского языка ---
@router.message(F.text == "📄 Generate Plan")
async def msg_generate_plan_en(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ You don't have an active subscription. Go to 💳 Subscription and get access.")

    # Получаем первого ученика (можно будет улучшить выбор)
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 You don't have any students. First add a student in the «👤 Students» section.",
            reply_markup=bottom_menu_students_kb(lang="EN")
        )
    
    student_id = students[0]["id"]
    student = await db.get_student_by_id(student_id)

    task = {
        "type": "generate_plan",
        "user_id": message.from_user.id,
        "student_id": student_id,
        "description": f"Study plan for student {student['name']} in {student['subject']}",
    }
    await _send_task(task)
    await message.answer("🕔 Generating study plan, wait for PDF…", reply_markup=bottom_menu_generation_kb(lang="EN"))

@router.message(F.text == "📝 Generate Tasks")
async def msg_generate_tasks_en(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ You don't have an active subscription. Go to 💳 Subscription and get access.")

    # Показываем список учеников для выбора
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 You don't have any students. First add a student in the «👤 Students» section.",
            reply_markup=bottom_menu_students_kb(lang="EN")
        )
    
    await state.set_state(TasksFSM.desc)
    await message.answer(
        "📝 **Task Generation**\n\n"
        "Describe what tasks to generate:\n"
        "• Topic or section\n"
        "• Task type (tests, problems, exercises)\n"
        "• Difficulty level\n"
        "• Number of tasks",
        reply_markup=bottom_menu_generation_kb(lang="EN")
    )

@router.message(F.text == "✅ Check HW")
async def msg_check_homework_en(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ You don't have an active subscription. Go to 💳 Subscription and get access.")

    # Получаем первого ученика (можно будет улучшить выбор)
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 You don't have any students. First add a student in the «👤 Students» section.",
            reply_markup=bottom_menu_students_kb(lang="EN")
        )
    
    student_id = students[0]["id"]
    await state.set_state(HomeworkCheckFSM.text)
    await state.update_data(student_id=student_id)
    
    await message.answer(
        "✅ **Homework Check Mode**\n\n"
        "Send a photo, PDF or text of homework.\n"
        "The bot will check it and give recommendations in PDF format.",
        reply_markup=bottom_menu_generation_kb(lang="EN")
    )

@router.message(F.text == "💬 Chat GPT")
async def msg_chat_gpt_en(message: Message, state: FSMContext):
    if not await has_active_sub(message.from_user.id):
        return await message.answer("❌ You don't have an active subscription. Go to 💳 Subscription and get access.")

    # Получаем первого ученика (можно будет улучшить выбор)
    students = await db.get_students_by_user(message.from_user.id)
    if not students:
        return await message.answer(
            "👤 You don't have any students. First add a student in the «👤 Students» section.",
            reply_markup=bottom_menu_students_kb(lang="EN")
        )
    
    student_id = students[0]["id"]
    await state.set_state(ChatGPTFSM.message)
    await state.update_data(student_id=student_id)
    
    await message.answer(
        "💬 **GPT Chat Mode**\n\n"
        "Write any question — the bot will answer you directly in the chat.\n"
        "Chat history is saved for each student.",
        reply_markup=bottom_menu_generation_kb(lang="EN")
    )

@router.message(F.text == "← Back to Students")
async def back_to_students_from_generation_en(message: Message):
    """Возврат к ученикам из генерации на английском"""
    students = await db.get_students_by_user(message.from_user.id)
    text = "Your students:" if students else "👤 You don't have any students yet."
    await message.answer(text, reply_markup=bottom_menu_students_kb(lang="EN"))
