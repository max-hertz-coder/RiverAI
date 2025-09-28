# bot_app/handlers/students.py

from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app.database import db
from bot_app.keyboards import students as student_kb

router = Router()


class AddStudentFSM(StatesGroup):
    name = State()
    grade = State()
    subject = State()
    level = State()
    notes = State()


class EditStudentFSM(StatesGroup):
    name = State()


async def _ensure_user(user_id: int, first_name: str):
    user = await db.get_user_by_tg_id(user_id)
    if user is None:
        user = await db.create_user(user_id, first_name)
    if user and user.get("plan") == "trial" and (user.get("students_limit") or 0) < 1:
        await db.set_subscription(
            user_id,
            "trial",
            1,
            user.get("subscription_expires") or (datetime.now() + timedelta(days=14)),
        )


def _no_students_text():
    return (
        "👤 У вас пока нет добавленных учеников.\n"
        "Вы можете легко сделать это с помощью кнопки ниже 👇"
    )


# --- Показ списка учеников ---
@router.callback_query(F.data == "show_students")
async def cb_show_students(callback: CallbackQuery):
    await _ensure_user(callback.from_user.id, callback.from_user.first_name or "")
    students = await db.get_students_by_user(callback.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))
    await callback.answer()


@router.message(F.text == "👤 Ученики")
async def msg_show_students(message: Message):
    await _ensure_user(message.from_user.id, message.from_user.first_name or "")
    students = await db.get_students_by_user(message.from_user.id)
    text = _no_students_text() if not students else "Ваши ученики:"
    await message.answer(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))


# --- Начало добавления ученика ---
@router.callback_query(F.data == "add_student")
async def cb_add_student(callback: CallbackQuery, state: FSMContext):
    user = callback.from_user
    await _ensure_user(user.id, user.first_name or "")
    user_data = await db.get_user_by_tg_id(user.id)
    students = await db.get_students_by_user(user.id)
    limit = user_data.get("students_limit") or user_data.get("max_students", 3) or (1 if user_data.get("plan") == "trial" else 3)
    if user_data and len(students) >= limit:
        await callback.message.answer(
            "🚫 Достигнут лимит по количеству учеников.\n\n"
            "Чтобы добавить больше, обновите тариф в разделе «Подписка»."
        )
        return
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await callback.message.answer(
        "Введите ассоциацию с учеником (например: «девочка 7 класс», «мальчик по физике»):"
    )
    await callback.answer()


@router.message(F.text == "➕ Добавить ученика")
async def msg_add_student(message: Message, state: FSMContext):
    user = message.from_user
    await _ensure_user(user.id, user.first_name or "")
    user_data = await db.get_user_by_tg_id(user.id)
    students = await db.get_students_by_user(user.id)
    limit = user_data.get("students_limit") or user_data.get("max_students", 3) or (1 if user_data.get("plan") == "trial" else 3)
    if user_data and len(students) >= limit:
        await message.answer(
            "🚫 Достигнут лимит по количеству учеников.\n\n"
            "Чтобы добавить больше, обновите тариф в разделе «Подписка»."
        )
        return
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await message.answer("Введите ассоциацию с учеником (например: «девочка 7 класс», «мальчик по физике»):")


# --- Шаги добавления ученика (FSM) ---
@router.message(AddStudentFSM.name)
async def add_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        return await message.reply("Имя не может быть пустым. Введите имя ученика:")
    await state.update_data(name=name)
    await state.set_state(AddStudentFSM.grade)
    await message.answer("Введите класс ученика (например: 7 класс; если не школьник — укажите возраст):")


@router.message(AddStudentFSM.grade)
async def add_grade(message: Message, state: FSMContext):
    grade = (message.text or "").strip()
    if not grade:
        return await message.reply("Класс/возраст не может быть пустым. Введите класс/возраст:")
    if grade == "-":
        grade = ""
    await state.update_data(grade=grade)
    await state.set_state(AddStudentFSM.subject)
    await message.answer("Введите предмет:")


@router.message(AddStudentFSM.subject)
async def add_subject(message: Message, state: FSMContext):
    subject = (message.text or "").strip()
    if not subject:
        return await message.reply("Предмет не может быть пустым. Введите предмет:")
    await state.update_data(subject=subject)
    await state.set_state(AddStudentFSM.level)
    await message.answer("Введите уровень ученика (низкий/средний/высокий или по 10-балльной шкале):")


@router.message(AddStudentFSM.level)
async def add_level(message: Message, state: FSMContext):
    level = (message.text or "").strip()
    if not level:
        return await message.reply("Уровень не может быть пустым. Введите уровень:")
    await state.update_data(level=level)
    await state.set_state(AddStudentFSM.notes)
    await message.answer("Введите заметки или '-' если без заметок:")


@router.message(AddStudentFSM.notes)
async def add_notes(message: Message, state: FSMContext):
    data = await state.get_data()
    notes = (message.text or "").strip()
    if notes == "-":
        notes = ""
    student_id = await db.add_student(
        message.from_user.id,
        data["name"],
        data["subject"],
        data.get("grade", ""),
        data["level"],
        notes,
    )
    await state.clear()
    if student_id:
        await message.answer(f"Ученик «{data['name']}» добавлен ✅")
    else:
        await message.answer("Не удалось добавить ученика.")
    # Возврат в список
    students = await db.get_students_by_user(message.from_user.id)
    await message.answer("Ваши ученики:", reply_markup=student_kb.students_list_kb(students, lang="RU"))


# --- Выбор ученика: показываем «досье» ТЕКСТОМ и под ним кнопки действий ---
@router.callback_query(F.data.startswith("student:"))
async def cb_select_student(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    sid = int(callback.data.split(":", 1)[1])
    student = await db.get_student(sid)
    if not student:
        return await callback.answer("Ученик не найден.", show_alert=True)

    name = student.get("name") or ""
    subject = student.get("subject") or ""
    grade = student.get("grade") or ""
    level = student.get("level") or ""
    notes = student.get("notes") or ""

    profile_text = (
        f"📋 Досье ученика\n"
        f"• Имя: {name}\n"
        f"• Предмет: {subject}\n"
        f"• Класс/возраст: {grade if grade else '—'}\n"
        f"• Уровень: {level}\n"
        f"• Заметки: {notes if notes else '—'}\n\n"
        f"Выберите действие:"
    )

    await callback.message.edit_text(
        profile_text,
        reply_markup=student_kb.student_actions_kb(sid, lang="RU"),
    )
    await callback.answer()


# --- Удаление ученика ---
@router.callback_query(F.data.startswith("delete_student:"))
async def cb_delete_student(callback: CallbackQuery):
    sid = int(callback.data.split(":", 1)[1])
    # Подтверждение через простую двухкнопочную клавиатуру
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=f"confirm_delete:{sid}:yes"),
            InlineKeyboardButton(text="Нет", callback_data=f"confirm_delete:{sid}:no"),
        ]
    ])
    await callback.message.edit_text("Удалить этого ученика?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery):
    _, sid_str, answer = callback.data.split(":")
    sid = int(sid_str)
    if answer == "yes":
        await db.delete_student(sid)
        students = await db.get_students_by_user(callback.from_user.id)
        text = _no_students_text() if not students else "Ваши ученики:"
        await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))
    else:
        # Возвращаемся к карточке ученика
        student = await db.get_student(sid)
        if student:
            name = student.get("name") or ""
            subject = student.get("subject") or ""
            grade = student.get("grade") or ""
            level = student.get("level") or ""
            notes = student.get("notes") or ""
            profile_text = (
                f"📋 Досье ученика\n"
                f"• Имя: {name}\n"
                f"• Предмет: {subject}\n"
                f"• Класс/возраст: {grade if grade else '—'}\n"
                f"• Уровень: {level}\n"
                f"• Заметки: {notes if notes else '—'}\n\n"
                f"Выберите действие:"
            )
            await callback.message.edit_text(profile_text, reply_markup=student_kb.student_actions_kb(sid, lang="RU"))
        else:
            students = await db.get_students_by_user(callback.from_user.id)
            text = _no_students_text() if not students else "Ваши ученики:"
            await callback.message.edit_text(text, reply_markup=student_kb.students_list_kb(students, lang="RU"))
    await callback.answer()
