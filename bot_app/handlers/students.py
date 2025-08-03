from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app.database import db
from bot_app.keyboards import students as student_kb
from bot_app.keyboards.main_menu import bottom_menu_students_kb, bottom_menu_student_actions_kb

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

# --- Показ списка учеников
@router.message(F.text == "👤 Ученики")
async def msg_show_students(message: Message):
    await _ensure_user(message.from_user.id, message.from_user.first_name or "")
    students = await db.get_students_by_user(message.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await message.answer(text, reply_markup=bottom_menu_students_kb())

# --- Начало добавления ученика
@router.message(F.text == "➕ Добавить ученика")
async def msg_add_student(message: Message, state: FSMContext):
    user = message.from_user
    await _ensure_user(user.id, user.first_name or "")
    user_data = await db.get_user_by_tg_id(user.id)
    students = await db.get_students_by_user(user.id)

    if user_data and len(students) >= user_data.get("max_students", 3):
        await message.answer(
            "🚫 Вы достигли лимита по количеству учеников.\n\n"
            "Чтобы добавить больше, обновите тариф в разделе «Подписка»."
        )
        return

    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await message.answer(
        "Введите ассоциацию с учеником (например: «девочка 7 класс», «мальчик по физике»):"
    )

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
    await message.answer("Введите уровень (например: начальный, средний, продвинутый):")

@router.message(AddStudentFSM.level)
async def add_level(message: Message, state: FSMContext):
    level = message.text.strip()
    if not level:
        return await message.reply("Уровень не может быть пустым. Введите уровень:")
    await state.update_data(level=level)
    await state.set_state(AddStudentFSM.notes)
    await message.answer("Введите дополнительные заметки (или отправьте '-' для пропуска):")

@router.message(AddStudentFSM.notes)
async def add_notes(message: Message, state: FSMContext):
    notes = message.text.strip()
    if notes == "-":
        notes = ""
    
    data = await state.get_data()
    student_id = await db.create_student(
        user_id=message.from_user.id,
        name=data["name"],
        subject=data["subject"],
        level=data["level"],
        notes=notes
    )
    
    await state.clear()
    await message.answer(
        f"✅ Ученик '{data['name']}' успешно добавлен!\n\n"
        f"📝 Предмет: {data['subject']}\n"
        f"📊 Уровень: {data['level']}\n"
        f"📋 Заметки: {notes if notes else 'не указаны'}",
        reply_markup=bottom_menu_students_kb()
    )

# --- Выбор ученика (через callback для совместимости)
@router.callback_query(F.data.startswith("student:"))
async def cb_select_student(callback: CallbackQuery):
    student_id = int(callback.data.split(":", 1)[1])
    student = await db.get_student_by_id(student_id)
    if not student:
        await callback.answer("Ученик не найден", show_alert=True)
        return
    
    text = f"👤 **{student['name']}**\n\n📝 Предмет: {student['subject']}\n📊 Уровень: {student['level']}"
    if student.get('notes'):
        text += f"\n📋 Заметки: {student['notes']}"
    
    await callback.message.edit_text(text, reply_markup=bottom_menu_student_actions_kb())

# --- Обработчики действий с учеником через нижнее меню
@router.message(F.text == "📄 Учебный план")
async def msg_generate_plan(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Выберите ученика для генерации учебного плана:", reply_markup=bottom_menu_students_kb())

@router.message(F.text == "📝 Задания")
async def msg_generate_tasks(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Выберите ученика для генерации заданий:", reply_markup=bottom_menu_students_kb())

@router.message(F.text == "✅ Проверить ДЗ")
async def msg_check_homework(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Выберите ученика для проверки домашнего задания:", reply_markup=bottom_menu_students_kb())

@router.message(F.text == "💬 Чат с GPT")
async def msg_chat_gpt(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Выберите ученика для чата с GPT:", reply_markup=bottom_menu_students_kb())

@router.message(F.text == "🗑 Удалить ученика")
async def msg_delete_student(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Выберите ученика для удаления:", reply_markup=bottom_menu_students_kb())

@router.message(F.text == "← К ученикам")
async def back_to_students(message: Message):
    """Возврат к списку учеников"""
    students = await db.get_students_by_user(message.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await message.answer(text, reply_markup=bottom_menu_students_kb())

# --- Обработчики для совместимости с callback
@router.callback_query(F.data.startswith("open_chat:"))
async def cb_open_chat(callback: CallbackQuery):
    student_id = int(callback.data.split(":", 1)[1])
    student = await db.get_student_by_id(student_id)
    if not student:
        await callback.answer("Ученик не найден", show_alert=True)
        return
    
    text = f"👤 **{student['name']}**\n\n📝 Предмет: {student['subject']}\n📊 Уровень: {student['level']}"
    if student.get('notes'):
        text += f"\n📋 Заметки: {student['notes']}"
    
    await callback.message.edit_text(text, reply_markup=bottom_menu_student_actions_kb())

@router.callback_query(F.data == "back:chat")
async def cb_back_to_chat_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    students = await db.get_students_by_user(callback.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await callback.message.edit_text(text, reply_markup=bottom_menu_students_kb())

@router.callback_query(F.data == "back:students")
async def cb_back_to_students(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    students = await db.get_students_by_user(callback.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await callback.message.edit_text(text, reply_markup=bottom_menu_students_kb())

# --- Удаление ученика
@router.callback_query(F.data.startswith("delete_student:"))
async def cb_delete_student(callback: CallbackQuery):
    student_id = int(callback.data.split(":", 1)[1])
    student = await db.get_student_by_id(student_id)
    if not student:
        await callback.answer("Ученик не найден", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"🗑 **Удаление ученика**\n\n"
        f"Вы действительно хотите удалить ученика '{student['name']}'?\n"
        f"Это действие нельзя отменить.",
        reply_markup=student_kb.confirm_delete_kb(student_id)
    )

@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery):
    parts = callback.data.split(":")
    student_id = int(parts[1])
    confirm = parts[2]
    
    if confirm == "yes":
        await db.delete_student(student_id)
        await callback.message.edit_text("✅ Ученик успешно удалён!")
        students = await db.get_students_by_user(callback.from_user.id)
        text = _no_students_text() if not students else "Ваши ученики:"
        await callback.message.answer(text, reply_markup=bottom_menu_students_kb())
    else:
        student = await db.get_student_by_id(student_id)
        if student:
            text = f"👤 **{student['name']}**\n\n📝 Предмет: {student['subject']}\n📊 Уровень: {student['level']}"
            if student.get('notes'):
                text += f"\n📋 Заметки: {student['notes']}"
            await callback.message.edit_text(text, reply_markup=bottom_menu_student_actions_kb())

# --- Редактирование ученика
@router.callback_query(F.data.startswith("edit_student:"))
async def cb_edit_student(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":", 1)[1])
    await state.set_state(EditStudentFSM.name)
    await state.update_data(student_id=student_id)
    await callback.message.edit_text("Введите новое имя ученика:")

@router.message(EditStudentFSM.name)
async def process_edit_name(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data["student_id"]
    new_name = message.text.strip()
    
    if not new_name:
        return await message.reply("Имя не может быть пустым. Введите новое имя:")
    
    await db.update_student_name(student_id, new_name)
    await state.clear()
    
    student = await db.get_student_by_id(student_id)
    text = f"✅ Имя ученика обновлено!\n\n👤 **{student['name']}**\n📝 Предмет: {student['subject']}\n📊 Уровень: {student['level']}"
    if student.get('notes'):
        text += f"\n📋 Заметки: {student['notes']}"
    
    await message.answer(text, reply_markup=bottom_menu_student_actions_kb())

# --- Обработчики для английского языка ---
@router.message(F.text == "📄 Generate Plan")
async def msg_generate_plan_en(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Select a student to generate a study plan:", reply_markup=bottom_menu_students_kb(lang="EN"))

@router.message(F.text == "📝 Generate Tasks")
async def msg_generate_tasks_en(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Select a student to generate tasks:", reply_markup=bottom_menu_students_kb(lang="EN"))

@router.message(F.text == "✅ Check HW")
async def msg_check_homework_en(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Select a student to check homework:", reply_markup=bottom_menu_students_kb(lang="EN"))

@router.message(F.text == "💬 Chat GPT")
async def msg_chat_gpt_en(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Select a student for GPT chat:", reply_markup=bottom_menu_students_kb(lang="EN"))

@router.message(F.text == "🗑 Delete Student")
async def msg_delete_student_en(message: Message, state: FSMContext):
    # Здесь нужно будет добавить логику для выбора ученика
    await message.answer("Select a student to delete:", reply_markup=bottom_menu_students_kb(lang="EN"))

@router.message(F.text == "← Back to Students")
async def back_to_students_en(message: Message):
    """Возврат к списку учеников на английском"""
    students = await db.get_students_by_user(message.from_user.id)
    text = "You don't have any students yet." if not students else "Your students:"
    await message.answer(text, reply_markup=bottom_menu_students_kb(lang="EN"))
