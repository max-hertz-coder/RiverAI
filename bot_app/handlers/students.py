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

async def _ensure_user(user_id: int, first_name: str):
    if await db.get_user_by_tg_id(user_id) is None:
        await db.create_user(user_id, first_name)

def _no_students_text():
    return (
        "👤 У Вас пока нет добавленных учеников.\n"
        "Вы можете легко сделать это с помощью кнопки ниже 👇"
    )

# --- Показ списка
@router.callback_query(F.data == "show_students")
async def cb_show_students(callback: CallbackQuery):
    await _ensure_user(callback.from_user.id, callback.from_user.first_name or "")
    students = await db.get_students_by_user(callback.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

@router.message(F.text == "👤 Ученики")
async def msg_show_students(message: Message):
    await _ensure_user(message.from_user.id, message.from_user.first_name or "")
    students = await db.get_students_by_user(message.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await message.answer(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

# --- Начало добавления ученика
@router.callback_query(F.data == "add_student")
@router.message(F.text == "➕ Добавить ученика")
async def start_add_student(event, state: FSMContext):
    user = event.from_user
    await _ensure_user(user.id, user.first_name or "")
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await event.answer("Введите ассоциацию с учеником (например: «девочка 7 класс», «мальчик по физике»):")

# --- FSM шаги добавления
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
        data["name"], data["subject"], data["level"], notes
    )
    await state.clear()
    if student_id:
        await message.answer(f"Ученик '{data['name']}' добавлен ✅")
    else:
        await message.answer("Не удалось добавить ученика.")
    await message.answer("Возвращаюсь в главное меню.", reply_markup=student_kb.back_button())

# --- Выбор ученика
@router.callback_query(F.data.startswith("student:"))
async def cb_select_student(callback: CallbackQuery):
    sid = int(callback.data.split(":", 1)[1])
    student = await db.get_student(sid)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)
    await callback.message.edit_text(
        f"Действия с учеником: {student['name']}",
        reply_markup=student_kb.student_actions_kb(sid, lang="RU")
    )

@router.callback_query(F.data.startswith("open_chat:"))
async def cb_open_chat(callback: CallbackQuery):
    sid = int(callback.data.split(":", 1)[1])
    student = await db.get_student(sid)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)
    header = f"👤 {student['name']} | Предмет: {student['subject']} | Уровень: {student['level']}"
    await callback.message.edit_text(header, reply_markup=chat_menu_kb(sid))

# --- Назад в меню ученика
@router.callback_query(F.data == "back:chat")
async def cb_back_to_chat_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sid = data.get("student_id")
    await state.clear()
    if sid:
        student = await db.get_student(sid)
        text = f"Действия с учеником: {student['name']}" if student else "Действия с учеником"
        await callback.message.edit_text(text, reply_markup=chat_menu_kb(sid))
    else:
        students = await db.get_students_by_user(callback.from_user.id)
        text = _no_students_text() if not students else "Ваши ученики:"
        await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

@router.callback_query(F.data == "back:students")
async def cb_back_to_students(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    students = await db.get_students_by_user(callback.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

# --- Удаление ученика
@router.callback_query(F.data.startswith("delete_student:"))
async def cb_delete_student(callback: CallbackQuery):
    sid = int(callback.data.split(":", 1)[1])
    await callback.message.edit_text(
        "Вы уверены, что хотите удалить этого ученика?",
        reply_markup=student_kb.confirm_delete_kb(sid, lang="RU")
    )

@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery):
    _, sid_str, answer = callback.data.split(":")
    sid = int(sid_str)
    if answer == "yes":
        await db.delete_student(sid)
        students = await db.get_students_by_user(callback.from_user.id)
        text = _no_students_text() if not students else "Ваши ученики:"
        await callback.message.edit_text(
            text,
            reply_markup=student_kb.students_list_kb(students, lang="RU")
        )
    else:
        student = await db.get_student(sid)
        text = f"Действия с учеником: {student['name']}"
        await callback.message.edit_text(
            text,
            reply_markup=student_kb.student_actions_kb(sid, lang="RU")
        )

# --- Редактирование ученика
@router.callback_query(F.data.startswith("edit_student:"))
async def cb_edit_student(callback: CallbackQuery, state: FSMContext):
    sid = int(callback.data.split(":", 1)[1])
    student = await db.get_student(sid)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)
    await state.set_state(EditStudentFSM.name)
    await state.update_data(student_id=sid)
    await callback.message.edit_text("Введите новое имя ученика:")

@router.message(EditStudentFSM.name)
async def process_edit_name(message: Message, state: FSMContext):
    data = await state.get_data()
    sid = data.get("student_id")
    new_name = message.text.strip()
    if not new_name:
        return await message.reply("Имя не может быть пустым.")
    await db.update_student(student_id=sid, name=new_name)
    await state.clear()
    student = await db.get_student(sid)
    await message.answer(
        f"Действия с учеником: {student['name']}",
        reply_markup=student_kb.student_actions_kb(sid, lang="RU")
    )
