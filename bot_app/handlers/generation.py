import json
import base64
import logging
from io import BytesIO

import aio_pika
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb, back_button

router = Router()
logger = logging.getLogger(__name__)

# --- OCR ---
@router.message(F.photo)
async def handle_photo_ocr(message: Message):
    bio = BytesIO()
    await message.photo[-1].download(destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {"type":"ocr","user_id":message.from_user.id,"file_data":b64,"file_name":"photo.jpg"}
    await _send_task(task)
    await message.answer("🔍 Распознавание текста запущено, ожидайте результат...")

@router.message(F.document)
async def handle_document_ocr(message: Message):
    bio = BytesIO()
    await message.document.download(destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type":"ocr",
        "user_id":message.from_user.id,
        "file_data":b64,
        "file_name":message.document.file_name or "file"
    }
    await _send_task(task)
    await message.answer("🔍 Распознавание текста запущено, ожидайте результат...")

# --- Генерация плана/заданий/решений/коррекции ---
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

# План
@router.callback_query(F.data.startswith("gen_plan:"))
async def cb_plan(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":",1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(PlanFSM.desc)
    await callback.message.edit_text("Опишите, что сгенерировать:", reply_markup=back_button("← Отмена","back:chat"))

@router.message(PlanFSM.desc)
async def proc_plan(msg: Message, state: FSMContext):
    d = await state.get_data()
    task = {"type":"generate_plan","user_id":msg.from_user.id,"student_id":d["student_id"],"description":msg.text}
    await _send_task(task)
    await msg.answer("🕔 Генерируется план, ожидайте...")
    await state.clear()

# Задания
@router.callback_query(F.data.startswith("gen_tasks:"))
async def cb_tasks(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":",1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(TasksFSM.desc)
    await callback.message.edit_text("Введите запрос для заданий:", reply_markup=back_button("← Отмена","back:chat"))

@router.message(TasksFSM.desc)
async def proc_tasks(msg: Message, state: FSMContext):
    d = await state.get_data()
    task = {"type":"generate_tasks","user_id":msg.from_user.id,"student_id":d["student_id"],"description":msg.text}
    await _send_task(task)
    await msg.answer("🕔 Генерируются задания, ожидайте...")
    await state.clear()

# Решения
@router.callback_query(F.data.startswith("solve_math:"))
async def cb_solve(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":",1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(SolveFSM.expr)
    await callback.message.edit_text("Введите выражение для решения:", reply_markup=back_button("← Отмена","back:chat"))

@router.message(SolveFSM.expr)
async def proc_solve(msg: Message, state: FSMContext):
    d = await state.get_data()
    task = {"type":"generate_solutions","user_id":msg.from_user.id,"student_id":d["student_id"],"expression":msg.text}
    await _send_task(task)
    await msg.answer("🕔 Генерируются решения, ожидайте...")
    await state.clear()

# Проверка ДЗ
@router.callback_query(F.data.startswith("check_hw:"))
async def cb_check(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":",1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(CheckFSM.file)
    await callback.message.edit_text("Загрузите файл для проверки:", reply_markup=back_button("← Отмена","back:chat"))

@router.message(CheckFSM.file, F.document)
async def proc_check(msg: Message, state: FSMContext):
    d = await state.get_data()
    bio = BytesIO()
    await msg.document.download(destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type":"check_homework",
        "user_id":msg.from_user.id,
        "student_id":d["student_id"],
        "file_data":b64,
        "file_name":msg.document.file_name or "hw"
    }
    await _send_task(task)
    await msg.answer("🕔 Проверка выполняется, ожидайте...")
    await state.clear()

# Коррекция заданий
@router.callback_query(F.data.startswith("correct_tasks:"))
async def cb_correct(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":",1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(CorrectFSM.file)
    await callback.message.edit_text("Загрузите файл для корректировки:", reply_markup=back_button("← Отмена","back:chat"))

@router.message(CorrectFSM.file, F.document)
async def proc_correct(msg: Message, state: FSMContext):
    d = await state.get_data()
    bio = BytesIO()
    await msg.document.download(destination=bio)
    b64 = base64.b64encode(bio.getvalue()).decode()
    task = {
        "type":"correct_tasks",
        "user_id":msg.from_user.id,
        "student_id":d["student_id"],
        "file_data":b64,
        "file_name":msg.document.file_name or "tasks"
    }
    await _send_task(task)
    await msg.answer("🕔 Коррекция выполняется, ожидайте...")
    await state.clear()

async def _send_task(task: dict):
    """Универсальный отправщик задачи в RabbitMQ."""
    try:
        conn = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER, password=config.RABBITMQ_PASS
        )
        ch = await conn.channel()
        await ch.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode()),
            routing_key=config.TASK_QUEUE
        )
        await conn.close()
    except Exception:
        logging.exception("Ошибка отправки задачи в очередь")
        raise
