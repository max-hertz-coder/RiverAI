from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app.database import db
from bot_app.keyboards import students as student_kb
from bot_app.keyboards.chat_menu import chat_menu_kb

router = Router()

class AddStudentFSM(StatesGroup):
    name = State()
    subject = State()
    level = State()
    notes = State()

class EditStudentFSM(StatesGroup):
    name = State()
    subject = State()
    level = State()
    notes = State()

async def _ensure_user(user_id: int, first_name: str):
    if await db.get_user_by_tg_id(user_id) is None:
        await db.create_user(user_id, first_name)

# Показ списка (по кнопке и по reply-клавиатуре)
@router.callback_query(F.data == "show_students")
async def cb_show_students(callback: CallbackQuery):
    await _ensure_user(callback.from_user.id, callback.from_user.first_name or "")
    students = await db.get_students_by_user(callback.from_user.id)
    text = "Ваши ученики:" + ("\n_(список пуст)_" if not students else "")
    await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

@router.message(F.text == "👤 Ученики")
async def msg_show_students(message: Message):
    await _ensure_user(message.from_user.id, message.from_user.first_name or "")
    students = await db.get_students_by_user(message.from_user.id)
    text = "Ваши ученики:" + ("\n_(список пуст)_" if not students else "")
    await message.answer(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

# Начало FSM добавления
@router.callback_query(F.data == "add_student")
@router.message(F.text == "➕ Добавить ученика")
async def start_add_student(event, state: FSMContext):
    user = event.from_user
    await _ensure_user(user.id, user.first_name or "")
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await (event.message if isinstance(event, CallbackQuery) else event).answer("Введите имя ученика:")

# Шаги FSM добавления
@router.message(AddStudentFSM.name)
async def add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        return await message.reply("Имя не может быть пустым. Введите имя ученика:")
    await state.update_data(name=name)
    await state.set_state(AddStudentFSM.subject)
    await message.answer("Введите предмет:")

@router.message(AddStudentFSM.subject)
async def add_subject(message: Message, state: FSMContext):
    subject = message.text.strip()
    if not subject:
        return await message.reply("Предмет не может быть пустым. Введите предмет:")
    await state.update_data(subject=subject)
    await state.set_state(AddStudentFSM.level)
    await message.answer("Введите уровень ученика:")

@router.message(AddStudentFSM.level)
async def add_level(message: Message, state: FSMContext):
    level = message.text.strip()
    if not level:
        return await message.reply("Уровень не может быть пустым. Введите уровень:")
    await state.update_data(level=level)
    await state.set_state(AddStudentFSM.notes)
    await message.answer("Введите заметки или '-' если без заметок:")

@router.message(AddStudentFSM.notes)
async def add_notes(message: Message, state: FSMContext):
    data = await state.get_data()
    notes = message.text.strip()
    if notes == "-":
        notes = ""
    student_id = await db.add_student(
        message.from_user.id,
        data["name"],
        data["subject"],
        data["level"],
        notes,
    )
    await state.clear()
    if student_id:
        await message.answer(f"Ученик '{data['name']}' добавлен ✅")
    else:
        await message.answer("Не удалось добавить ученика.")
    await message.answer("Возвращаюсь в главное меню.", reply_markup=student_kb.back_button())

# Выбор ученика и действия
@router.callback_query(F.data.startswith("student:"))
async def cb_select_student(callback: CallbackQuery):
    sid = int(callback.data.split(":",1)[1])
    student = await db.get_student(sid)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)
    text = f"Действия с учеником: {student['name']}"
    await callback.message.edit_text(text, reply_markup=student_kb.student_actions_kb(sid, lang="RU"))

@router.callback_query(F.data.startswith("open_chat:"))
async def cb_open_chat(callback: CallbackQuery):
    sid = int(callback.data.split(":",1)[1])
    student = await db.get_student(sid)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)
    header = f"👤 {student['name']} | Предмет: {student['subject']} | Уровень: {student['level']}"
    await callback.message.edit_text(header, reply_markup=chat_menu_kb(sid, lang="RU"))

# Редактирование и удаление — оставляем без изменений, главное ensure_user перед CRUD
