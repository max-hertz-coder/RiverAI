from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import database
from bot_app.keyboards import students as student_kb

router = Router()

# Define states for adding/editing students
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

# Show list of students
@router.callback_query(F.data == "show_students")
async def cb_show_students(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    # Query DB for students of this user
    students = await database.db.get_students_by_user(user_id)
    lang = "RU"
    text = "Ваши ученики:" if lang == "RU" else "Your students:"
    if not students:
        text += ("\n_(список пуст)_" if lang == "RU" else "\n_(no students yet)_")
    await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang))

# Start Add Student flow
@router.callback_query(F.data == "add_student")
async def cb_add_student(callback: CallbackQuery, state: FSMContext):
    """Initiate the process to add a new student (FSM)."""
    await callback.answer()  # acknowledge button press
    # Ask for student name
    await state.set_state(AddStudentFSM.name)
    await callback.message.edit_text("Введите имя ученика:")

# Step 1: Receive student name
@router.message(AddStudentFSM.name)
async def add_student_name_step(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.reply("Имя не может быть пустым. Введите имя ученика:")
        return
    # Save name and ask for subject
    await state.update_data(name=name)
    await state.set_state(AddStudentFSM.subject)
    await message.answer("Введите предмет/предметы, которые изучает ученик:")

# Step 2: Receive student subject(s)
@router.message(AddStudentFSM.subject)
async def add_student_subject_step(message: Message, state: FSMContext):
    subject = message.text.strip()
    if not subject:
        await message.reply("Предмет не может быть пустым. Введите предметы:")
        return
    await state.update_data(subject=subject)
    await state.set_state(AddStudentFSM.level)
    await message.answer("Введите уровень ученика (например, начальный, средний, продвинутый):")

# Step 3: Receive student level
@router.message(AddStudentFSM.level)
async def add_student_level_step(message: Message, state: FSMContext):
    level = message.text.strip()
    if not level:
        await message.reply("Уровень не может быть пустым. Введите уровень ученика:")
        return
    await state.update_data(level=level)
    await state.set_state(AddStudentFSM.notes)
    await message.answer("Введите заметки (особенности) или '-' если без заметок:")

# Step 4: Receive student notes (optional)
@router.message(AddStudentFSM.notes)
async def add_student_notes_step(message: Message, state: FSMContext):
    notes = message.text.strip()
    if notes == "-":
        notes = ""  # treat "-" as no notes
    data = await state.get_data()
    name = data.get("name")
    subject = data.get("subject")
    level = data.get("level")
    user_id = message.from_user.id
    # Save new student to DB
    student_id = await database.db.add_student(user_id, name, subject, level, notes)
    # Finish FSM
    await state.clear()
    if student_id:
        await message.answer(f"Ученик '{name}' добавлен ✅")
    else:
        await message.answer("Не удалось добавить ученика. Попробуйте еще раз.")
    # Optionally, show updated student list or main menu
    # Here, we send main menu again:
    await message.answer("Возвращаюсь в главное меню.", reply_markup=student_kb.back_button())

# Handle selecting a student from the list (show actions menu)
@router.callback_query(F.data.startswith("student:"))
async def cb_select_student(callback: CallbackQuery):
    data = callback.data.split(":")
    if len(data) < 2:
        return
    student_id = int(data[1])
    # Fetch student to get name (for display)
    student = await database.db.get_student(student_id)
    if not student:
        await callback.answer("Ученик не найден.", show_alert=True)
        return
    text = f"Действия с учеником: {student['name']}"
    await callback.message.edit_text(text, reply_markup=student_kb.student_actions_kb(student_id, lang="RU"))

# Open chat context (i.e., go to functions menu for this student)
@router.callback_query(F.data.startswith("open_chat:"))
async def cb_open_chat(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[1])
    student = await database.db.get_student(student_id)
    if not student:
        await callback.answer("Ученик не найден.", show_alert=True)
        return
    header = f"👤 {student['name']} | Предмет: {student['subject']} | Уровень: {student['level']}"
    # Show the chat-context menu (generate plan, tasks, etc.)
    await callback.message.edit_text(header, reply_markup=student_kb.chat_menu_kb(student_id, lang="RU"))

# Initiate Edit Student flow
@router.callback_query(F.data.startswith("edit_student:"))
async def cb_edit_student(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    student = await database.db.get_student(student_id)
    if not student:
        await callback.answer("Ученик не найден.", show_alert=True)
        return
    # Store student_id and current data in FSM context
    await state.update_data(student_id=student_id, current_name=student["name"],
                            current_subject=student["subject"], current_level=student["level"], current_notes=student["notes"])
    # Ask for new name
    await state.set_state(EditStudentFSM.name)
    await callback.message.edit_text(f"Текущее имя: {student['name']}\nВведите новое имя (или /skip, чтобы оставить без изменений):")

# Edit name step
@router.message(EditStudentFSM.name)
async def edit_student_name_step(message: Message, state: FSMContext):
    data = await state.get_data()
    new_name = message.text.strip()
    if new_name == "" or new_name.lower() == "/skip":
        new_name = data.get("current_name")
    await state.update_data(new_name=new_name)
    await state.set_state(EditStudentFSM.subject)
    await message.answer(f"Текущий предмет: {data.get('current_subject')}\nВведите новый предмет (или /skip):")

# Edit subject step
@router.message(EditStudentFSM.subject)
async def edit_student_subject_step(message: Message, state: FSMContext):
    data = await state.get_data()
    new_subject = message.text.strip()
    if new_subject == "" or new_subject.lower() == "/skip":
        new_subject = data.get("current_subject")
    await state.update_data(new_subject=new_subject)
    await state.set_state(EditStudentFSM.level)
    await message.answer(f"Текущий уровень: {data.get('current_level')}\nВведите новый уровень (или /skip):")

# Edit level step
@router.message(EditStudentFSM.level)
async def edit_student_level_step(message: Message, state: FSMContext):
    data = await state.get_data()
    new_level = message.text.strip()
    if new_level == "" or new_level.lower() == "/skip":
        new_level = data.get("current_level")
    await state.update_data(new_level=new_level)
    await state.set_state(EditStudentFSM.notes)
    current_notes = data.get("current_notes")
    curr_display = current_notes if current_notes else "(нет)"
    await message.answer(f"Текущие заметки: {curr_display}\nВведите новые заметки (или /skip):")

# Edit notes step
@router.message(EditStudentFSM.notes)
async def edit_student_notes_step(message: Message, state: FSMContext):
    data = await state.get_data()
    new_notes = message.text.strip()
    if new_notes.lower() == "/skip":
        new_notes = data.get("current_notes") or ""
    student_id = data.get("student_id")
    # Update DB
    await database.db.update_student(student_id, data.get("new_name"), data.get("new_subject"), data.get("new_level"), new_notes)
    await message.answer("Данные ученика обновлены ✅")
    await state.clear()
    # Return to student list
    students = await database.db.get_students_by_user(message.from_user.id)
    text = "Ваши ученики:"
    await message.answer(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))

# Delete student (confirmation prompt)
@router.callback_query(F.data.startswith("delete_student:"))
async def cb_delete_student(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[1])
    student = await database.db.get_student(student_id)
    if not student:
        await callback.answer("Ученик не найден.", show_alert=True)
        return
    # Ask for confirmation
    await callback.message.edit_text(f"Удалить ученика {student['name']}? Вы уверены?", 
                                     reply_markup=student_kb.confirm_delete_kb(student_id, lang="RU"))

# Handle delete confirmation
@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery):
    parts = callback.data.split(":")
    # Format: confirm_delete:<id>:yes or no
    if len(parts) < 3:
        return
    student_id = int(parts[1])
    choice = parts[2]
    if choice == "yes":
        # Perform deletion
        await database.db.delete_student(student_id)
        await callback.answer("Удалено", show_alert=False)
        # After deletion, show updated student list
        students = await database.db.get_students_by_user(callback.from_user.id)
        text = "Ученик удалён.\nВаши ученики:"
        await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))
    else:
        # choice == "no": cancel deletion, go back to student actions menu
        student = await database.db.get_student(student_id)
        if student:
            text = f"Действия с учеником: {student['name']}"
            await callback.message.edit_text(text, reply_markup=student_kb.student_actions_kb(student_id, lang="RU"))
