import json
import base64
import logging
from io import BytesIO

import aio_pika
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config, rabbit_channel
from bot_app.keyboards.chat_menu import chat_menu_kb
from bot_app.keyboards.main_menu import back_button
from bot_app.handlers.chatgpt import ChatState

router = Router()
logger = logging.getLogger(__name__)

async def _send_task(task: dict):
    """Универсальный метод отправки задачи в RabbitMQ."""
    try:
        if rabbit_channel:
            # Используем существующее соединение с RabbitMQ для отправки задачи
            await rabbit_channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(task).encode("utf-8")),
                routing_key=config.TASK_QUEUE
            )
        else:
            # Если по какой-то причине нет готового канала, устанавливаем временное соединение
            conn = await aio_pika.connect_robust(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                login=config.RABBITMQ_USER,
                password=config.RABBITMQ_PASS,
            )
            ch = await conn.channel()
            await ch.default_exchange.publish(
                aio_pika.Message(body=json.dumps(task).encode("utf-8")),
                routing_key=config.TASK_QUEUE
            )
            await conn.close()
    except Exception:
        logger.exception("Ошибка отправки задачи в очередь")
        raise

#
# OCR: обработка фотографий и документов (распознавание текста)
#
@router.message(F.photo)
async def handle_photo_ocr(message: Message):
    bio = BytesIO()
    # Загрузка фото через Bot API (aiogram v3)
    bot = Bot.get_current()
    file_id = message.photo[-1].file_id
    await bot.download(file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type": "ocr",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": "photo.jpg",
    }
    await _send_task(task)
    await message.answer("🔍 Распознавание текста запущено, ожидайте результат...")

@router.message(F.document)
async def handle_document_ocr(message: Message):
    bio = BytesIO()
    # Загрузка документа через Bot API
    bot = Bot.get_current()
    file_id = message.document.file_id
    await bot.download(file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type": "ocr",
        "user_id": message.from_user.id,
        "student_id": None,
        "file_data": b64,
        "file_name": message.document.file_name or "file",
    }
    await _send_task(task)
    await message.answer("🔍 Распознавание текста запущено, ожидайте результат...")

#
# FSM-состояния для последовательных действий
#
class PlanFSM(StatesGroup):
    desc = State()

class TasksFSM(StatesGroup):
    desc = State()

class SolveFSM(StatesGroup):
    expr = State()

class CheckFSM(StatesGroup):
    file = State()

class CorrectFSM(StatesGroup):
    file = State()

class RefineCheckFSM(StatesGroup):
    notes = State()

#
# Генерация учебного плана
#
@router.callback_query(F.data.startswith("generate_plan:"))
async def cb_plan(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(PlanFSM.desc)
    await callback.message.edit_text(
        "Опишите, что сгенерировать (учебный план):",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(PlanFSM.desc)
async def proc_plan(message: Message, state: FSMContext):
    d = await state.get_data()
    task = {
        "type": "generate_plan",
        "user_id": message.from_user.id,
        "student_id": d["student_id"],
        "description": message.text,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируется учебный план, ожидайте...")
    await state.clear()

#
# Генерация заданий
#
@router.callback_query(F.data.startswith("generate_tasks:"))
async def cb_tasks(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(TasksFSM.desc)
    await callback.message.edit_text(
        "Введите запрос для генерации заданий:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(TasksFSM.desc)
async def proc_tasks(message: Message, state: FSMContext):
    d = await state.get_data()
    task = {
        "type": "generate_tasks",
        "user_id": message.from_user.id,
        "student_id": d["student_id"],
        "description": message.text,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()

#
# Генерация решений по математическому выражению
#
@router.callback_query(F.data.startswith("solve_math:"))
async def cb_solve(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(SolveFSM.expr)
    await callback.message.edit_text(
        "Введите математическое выражение для решения:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(SolveFSM.expr)
async def proc_solve(message: Message, state: FSMContext):
    d = await state.get_data()
    task = {
        "type": "generate_solutions",
        "user_id": message.from_user.id,
        "student_id": d["student_id"],
        "expression": message.text,
    }
    await _send_task(task)
    await message.answer("🕔 Генерируются решения, ожидайте...")
    await state.clear()

#
# Проверка домашней работы
#
@router.callback_query(F.data.startswith("check_hw:"))
async def cb_check(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(CheckFSM.file)
    await callback.message.edit_text(
        "Загрузите файл домашней работы для проверки:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(CheckFSM.file, F.document)
async def proc_check(message: Message, state: FSMContext):
    d = await state.get_data()
    bio = BytesIO()
    bot = Bot.get_current()
    file_id = message.document.file_id
    await bot.download(file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type": "check_homework",
        "user_id": message.from_user.id,
        "student_id": d["student_id"],
        "file_data": b64,
        "file_name": message.document.file_name or "homework",
    }
    await _send_task(task)
    await message.answer("🕔 Домашняя работа отправлена на проверку, ожидайте...")
    await state.clear()

#
# Коррекция заданий (загрузка файла для корректировки заданий)
#
@router.callback_query(F.data.startswith("correct_tasks:"))
async def cb_correct(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(CorrectFSM.file)
    await callback.message.edit_text(
        "Загрузите файл с заданиями для корректировки:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(CorrectFSM.file, F.document)
async def proc_correct(message: Message, state: FSMContext):
    d = await state.get_data()
    bio = BytesIO()
    bot = Bot.get_current()
    file_id = message.document.file_id
    await bot.download(file_id, destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type": "correct_tasks",
        "user_id": message.from_user.id,
        "student_id": d["student_id"],
        "file_data": b64,
        "file_name": message.document.file_name or "tasks",
    }
    await _send_task(task)
    await message.answer("🕔 Задания отправлены на корректировку, ожидайте...")
    await state.clear()

#
# Уточнение сгенерированных результатов (Refine функционал)
#
@router.callback_query(F.data.startswith("refine_plan:"))
async def cb_refine_plan(callback: CallbackQuery, state: FSMContext):
    """Начало процесса уточнения учебного плана."""
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(PlanFSM.desc)
    await callback.message.edit_text(
        "Опишите, как скорректировать учебный план:",
        reply_markup=back_button("← Отмена", "back:chat")
    )
    # Пользователь введет новое описание, обработается в proc_plan

@router.callback_query(F.data.startswith("refine_tasks:"))
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    """Начало процесса уточнения сгенерированных заданий."""
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(TasksFSM.desc)
    await callback.message.edit_text(
        "Опишите, как скорректировать задания:",
        reply_markup=back_button("← Отмена", "back:chat")
    )
    # Далее ввод пользователя обработается в proc_tasks

@router.callback_query(F.data.startswith("refine_check:"))
async def cb_refine_check(callback: CallbackQuery, state: FSMContext):
    """Начало процесса корректировки отчета проверки домашнего задания."""
    sid = int(callback.data.split(":", 1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(RefineCheckFSM.notes)
    await callback.message.edit_text(
        "Введите комментарии для корректировки отчёта:",
        reply_markup=back_button("← Отмена", "back:chat")
    )

@router.message(RefineCheckFSM.notes)
async def proc_refine_check(message: Message, state: FSMContext):
    """Отправляет задачу refine_check с комментариями для повторной проверки ДЗ."""
    d = await state.get_data()
    notes = message.text.strip()
    task = {
        "type": "refine_check",
        "user_id": message.from_user.id,
        "student_id": d.get("student_id"),
        "notes": notes
    }
    await _send_task(task)
    await message.answer("🕔 Повторная проверка запущена, ожидайте результат...")
    await state.clear()

#
# Отправка сгенерированных заданий в GPT-чат
#
@router.callback_query(F.data.startswith("send_tasks:"))
async def cb_send_tasks(callback: CallbackQuery, state: FSMContext):
    """Отправляет сгенерированные задания в личный чат с GPT (контекст ученика)."""
    sid = int(callback.data.split(":", 1)[1])
    # Получаем текст заданий из сообщения (после первой строки "📝 Задания:")
    tasks_text = ""
    if callback.message and callback.message.text:
        parts = callback.message.text.split("\n", 1)
        if len(parts) > 1:
            tasks_text = parts[1]
        else:
            tasks_text = parts[0]
    # Активируем состояние чата для данного ученика
    await state.update_data(student_id=sid)
    await state.set_state(ChatState.active)
    # Отправляем сообщение в очередь для GPT-чат воркера
    task = {
        "type": "chat",
        "user_id": callback.from_user.id,
        "student_id": sid,
        "message": tasks_text
    }
    try:
        await _send_task(task)
    except Exception:
        logger.exception("Ошибка отправки задания в чат")
        return await callback.message.answer("⚠️ Не удалось отправить задания в чат, попробуйте позже.")
    await callback.message.answer("💭 Задания отправлены ИИ, ожидайте ответ…", reply_markup=chat_menu_kb(sid))

#
# Сохранение результатов на Яндекс.Диск
#
@router.callback_query(F.data.startswith("save_plan:"))
async def cb_save_plan(callback: CallbackQuery):
    """Сохраняет сгенерированный учебный план на Я.Диске пользователя."""
    sid = int(callback.data.split(":", 1)[1])
    plan_text = ""
    if callback.message and callback.message.text:
        parts = callback.message.text.split("\n", 1)
        if len(parts) > 1:
            plan_text = parts[1]
        else:
            plan_text = parts[0]
    task = {
        "type": "save_plan",
        "user_id": callback.from_user.id,
        "student_id": sid,
        "plan_text": plan_text
    }
    await _send_task(task)
    await callback.message.answer("💾 Сохранение плана на Я.Диске...")

@router.callback_query(F.data.startswith("save_tasks:"))
async def cb_save_tasks(callback: CallbackQuery):
    """Сохраняет сгенерированные задания в PDF на Я.Диске пользователя."""
    sid = int(callback.data.split(":", 1)[1])
    tasks_text = ""
    if callback.message and callback.message.text:
        parts = callback.message.text.split("\n", 1)
        if len(parts) > 1:
            tasks_text = parts[1]
        else:
            tasks_text = parts[0]
    task = {
        "type": "save_tasks",
        "user_id": callback.from_user.id,
        "student_id": sid,
        "tasks_text": tasks_text
    }
    await _send_task(task)
    await callback.message.answer("💾 Сохранение заданий (PDF) на Я.Диске...")

@router.callback_query(F.data.startswith("save_check:"))
async def cb_save_check(callback: CallbackQuery):
    """Сохраняет отчет проверки ДЗ на Я.Диске пользователя."""
    sid = int(callback.data.split(":", 1)[1])
    report_text = ""
    if callback.message and callback.message.text:
        parts = callback.message.text.split("\n", 1)
        if len(parts) > 1:
            report_text = parts[1]
        else:
            report_text = parts[0]
    task = {
        "type": "save_check",
        "user_id": callback.from_user.id,
        "student_id": sid,
        "report_text": report_text
    }
    await _send_task(task)
    await callback.message.answer("💾 Сохранение отчёта проверки на Я.Диске...")
