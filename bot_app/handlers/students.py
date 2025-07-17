from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app.database import db
from bot_app.keyboards import students as student_kb

router = Router()

# FSM для добавления/редактирования ученика
class AddStudentFSM(StatesGroup):
    name    = State()
    subject = State()
    level   = State()
    notes   = State()

class EditStudentFSM(StatesGroup):
    name    = State()
    subject = State()
    level   = State()
    notes   = State()

# 1) Показать список учеников
@router.callback_query(F.data == "show_students")
async def cb_show_students(callback: CallbackQuery):
    user_id = callback.from_user.id
    # Гарантируем, что пользователь есть в БД
    if await db.get_user_by_tg_id(user_id) is None:
        await db.create_user(user_id, callback.from_user.first_name or "")
    students = await db.get_students_by_user(user_id)
    text = "Ваши ученики:" if True else "Your students:"
    if not students:
        text += "\n_(список пуст)_" 
    await callback.message.edit_text(
        text,
        reply_markup=student_kb.students_list_kb(students, lang="RU"),
    )

# 2) Начало FSM добавления ученика
@router.callback_query(F.data == "add_student")
async def cb_add_student(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await db.get_user_by_tg_id(callback.from_user.id) is None:
        await db.create_user(callback.from_user.id, callback.from_user.first_name or "")
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await callback.message.edit_text("Введите имя ученика:")

# Шаг 1: имя
@router.message(AddStudentFSM.name)
async def add_student_name_step(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.reply("Имя не может быть пустым. Введите имя ученика:")
        return
    await state.update_data(name=name)
    await state.set_state(AddStudentFSM.subject)
    await message.answer("Введите предмет:")

# Шаг 2: предмет
@router.message(AddStudentFSM.subject)
async def add_student_subject_step(message: Message, state: FSMContext):
    subject = message.text.strip()
    if not subject:
        await message.reply("Предмет не может быть пустым. Введите предмет:")
        return
    await state.update_data(subject=subject)
    await state.set_state(AddStudentFSM.level)
    await message.answer("Введите уровень ученика:")

# Шаг 3: уровень
@router.message(AddStudentFSM.level)
async def add_student_level_step(message: Message, state: FSMContext):
    level = message.text.strip()
    if not level:
        await message.reply("Уровень не может быть пустым. Введите уровень:")
        return
    await state.update_data(level=level)
    await state.set_state(AddStudentFSM.notes)
    await message.answer("Введите заметки или '-' если без заметок:")

# Шаг 4: заметки и сохранение
@router.message(AddStudentFSM.notes)
async def add_student_notes_step(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if await db.get_user_by_tg_id(user_id) is None:
        await db.create_user(user_id, message.from_user.first_name or "")

    notes = message.text.strip()
    if notes == "-":
        notes = ""
    data = await state.get_data()
    student_id = await db.add_student(
        user_id,
        data["name"],
        data["subject"],
        data["level"],
        notes,
    )
    await state.clear()

    if student_id:
        await message.answer(f"Ученик '{data['name']}' добавлен ✅")
    else:
        await message.answer("Не удалось добавить ученика. Попробуйте ещё раз.")

    # Возврат в главное меню
    await message.answer(
        "Возвращаюсь в главное меню.",
        reply_markup=student_kb.back_button(),
    )

# Далее аналогично: cb_select_student, cb_open_chat, cb_edit_student и т.д.
# Но **важно** на всех точках, где используется user_id, сначала проверять:
# if await db.get_user_by_tg_id(user_id) is None: await db.create_user(...)
# чтобы избежать ForeignKeyViolationError.

class AddStudentFSM(StatesGroup):
    name    = State()
    subject = State()
    level   = State()
    notes   = State()


class EditStudentFSM(StatesGroup):
    name    = State()
    subject = State()
    level   = State()
    notes   = State()


async def _ensure_user(user_id: int, first_name: str):
    """Создать запись в users, если ещё нет."""
    if await db.get_user_by_tg_id(user_id) is None:
        await db.create_user(user_id, first_name or "")


# 1) Показываем список учеников (по Callback и по Reply-кнопке)
@router.callback_query(F.data == "show_students")
async def cb_show_students(callback: CallbackQuery):
    await _ensure_user(callback.from_user.id, callback.from_user.first_name)
    students = await db.get_students_by_user(callback.from_user.id)
    text = "Ваши ученики:" + ("\n_(список пуст)_" if not students else "")
    await callback.message.edit_text(
        text,
        reply_markup=student_kb.students_list_kb(students, lang="RU")
    )


@router.message(F.text == "👤 Ученики")
async def msg_show_students(message: Message):
    await _ensure_user(message.from_user.id, message.from_user.first_name)
    students = await db.get_students_by_user(message.from_user.id)
    text = "Ваши ученики:" + ("\n_(список пуст)_" if not students else "")
    await message.answer(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))


# 2) Начинаем FSM добавления (Callback и Reply)
@router.callback_query(F.data == "add_student")
async def cb_add_student(callback: CallbackQuery, state: FSMContext):
    await _ensure_user(callback.from_user.id, callback.from_user.first_name)
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await callback.message.edit_text("Введите имя ученика:")


@router.message(F.text == "➕ Добавить ученика")
async def msg_add_student(message: Message, state: FSMContext):
    await _ensure_user(message.from_user.id, message.from_user.first_name)
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await message.answer("Введите имя ученика:")


# Шаги FSM добавления
@router.message(AddStudentFSM.name)
async def add_student_name_step(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        return await message.reply("Имя не может быть пустым. Введите имя ученика:")
    await state.update_data(name=name)
    await state.set_state(AddStudentFSM.subject)
    await message.answer("Введите предмет:")


@router.message(AddStudentFSM.subject)
async def add_student_subject_step(message: Message, state: FSMContext):
    subject = message.text.strip()
    if not subject:
        return await message.reply("Предмет не может быть пустым. Введите предмет:")
    await state.update_data(subject=subject)
    await state.set_state(AddStudentFSM.level)
    await message.answer("Введите уровень ученика:")


@router.message(AddStudentFSM.level)
async def add_student_level_step(message: Message, state: FSMContext):
    level = message.text.strip()
    if not level:
        return await message.reply("Уровень не может быть пустым. Введите уровень ученика:")
    await state.update_data(level=level)
    await state.set_state(AddStudentFSM.notes)
    await message.answer("Введите заметки или '-' если без заметок:")


@router.message(AddStudentFSM.notes)
async def add_student_notes_step(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await _ensure_user(user_id, message.from_user.first_name)

    notes = message.text.strip()
    if notes == "-":
        notes = ""
    data = await state.get_data()
    student_id = await db.add_student(
        user_id,
        data["name"],
        data["subject"],
        data["level"],
        notes,
    )
    await state.clear()

    if student_id:
        await message.answer(f"Ученик '{data['name']}' добавлен ✅")
    else:
        await message.answer("Не удалось добавить ученика. Попробуйте ещё раз.")

    # Возвращаем главное меню
    await message.answer(
        "Возвращаюсь в главное меню.",
        reply_markup=student_kb.back_button()
    )


# 3) Выбор конкретного ученика из списка
@router.callback_query(F.data.startswith("student:"))
async def cb_select_student(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[1])
    student = await db.get_student(student_id)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)

    text = f"Действия с учеником: {student['name']}"
    await callback.message.edit_text(
        text,
        reply_markup=student_kb.student_actions_kb(student_id, lang="RU")
    )


# 4) Переход в контекст чата для ученика
@router.callback_query(F.data.startswith("open_chat:"))
async def cb_open_chat(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[1])
    student = await db.get_student(student_id)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)

    header = f"👤 {student['name']} | Предмет: {student['subject']} | Уровень: {student['level']}"
    await callback.message.edit_text(
        header,
        reply_markup=student_kb.chat_menu_kb(student_id, lang="RU")
    )


# 5) FSM редактирования информации
@router.callback_query(F.data.startswith("edit_student:"))
async def cb_edit_student(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    student = await db.get_student(student_id)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)

    # Сохраняем текущее в context
    await state.update_data(
        student_id=student_id,
        current_name=student["name"],
        current_subject=student["subject"],
        current_level=student["level"],
        current_notes=student["notes"],
    )
    await state.set_state(EditStudentFSM.name)
    await callback.message.edit_text(
        f"Текущее имя: {student['name']}\n"
        "Введите новое имя (или /skip, чтобы оставить без изменений):"
    )


@router.message(EditStudentFSM.name)
async def edit_student_name_step(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text.strip()
    new_name = data["current_name"] if text.lower() in ("", "/skip") else text
    await state.update_data(new_name=new_name)
    await state.set_state(EditStudentFSM.subject)
    await message.answer(
        f"Текущий предмет: {data['current_subject']}\n"
        "Введите новый предмет (или /skip):"
    )


@router.message(EditStudentFSM.subject)
async def edit_student_subject_step(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text.strip()
    new_subject = data["current_subject"] if text.lower() in ("", "/skip") else text
    await state.update_data(new_subject=new_subject)
    await state.set_state(EditStudentFSM.level)
    await message.answer(
        f"Текущий уровень: {data['current_level']}\n"
        "Введите новый уровень (или /skip):"
    )


@router.message(EditStudentFSM.level)
async def edit_student_level_step(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text.strip()
    new_level = data["current_level"] if text.lower() in ("", "/skip") else text
    await state.update_data(new_level=new_level)
    await state.set_state(EditStudentFSM.notes)
    curr = data["current_notes"] or "(нет)"
    await message.answer(
        f"Текущие заметки: {curr}\n"
        "Введите новые заметки (или /skip):"
    )


@router.message(EditStudentFSM.notes)
async def edit_student_notes_step(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text.strip()
    new_notes = data["current_notes"] if text.lower() == "/skip" else text
    sid = data["student_id"]

    await db.update_student(
        sid,
        data["new_name"],
        data["new_subject"],
        data["new_level"],
        new_notes,
    )
    await message.answer("Данные ученика обновлены ✅")
    await state.clear()

    # Возвращаем список
    students = await db.get_students_by_user(message.from_user.id)
    await message.answer(
        "Ваши ученики:",
        reply_markup=student_kb.students_list_kb(students, lang="RU")
    )


# 6) Удаление ученика
@router.callback_query(F.data.startswith("delete_student:"))
async def cb_delete_student(callback: CallbackQuery):
    student_id = int(callback.data.split(":")[1])
    student = await db.get_student(student_id)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)

    await callback.message.edit_text(
        f"Удалить ученика {student['name']}? Вы уверены?",
        reply_markup=student_kb.confirm_delete_kb(student_id, lang="RU")
    )


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        return
    sid = int(parts[1])
    confirm = parts[2]

    if confirm == "yes":
        await db.delete_student(sid)
        await callback.answer("Ученик удалён")
        students = await db.get_students_by_user(callback.from_user.id)
        await callback.message.edit_text(
            "Ученик удалён.\nВаши ученики:",
            reply_markup=student_kb.students_list_kb(students, lang="RU")
        )
    else:
        # отмена — возвращаем меню действий
        student = await db.get_student(sid)
        await callback.message.edit_text(
            f"Действия с учеником: {student['name']}",
            reply_markup=student_kb.student_actions_kb(sid, lang="RU")
        )