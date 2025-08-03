from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram import F
from aiogram.fsm.context import FSMContext

from bot_app.keyboards.main_menu import bottom_menu_kb
from bot_app.keyboards.settings import yandex_prompt_kb
from bot_app import database
from bot_app.utils.encryption import decrypt_str

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие и показ меню."""
    first_name = message.from_user.first_name or ""
    user_id = message.from_user.id
    user = await database.db.get_user_by_tg_id(user_id)

    lang = user["language"] if user and "language" in user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?"
    )

    # Показываем только нижнее меню
    await message.reply(welcome, reply_markup=bottom_menu_kb(lang))

    # Предложение подключить Яндекс.Диск
    if user:
        token_enc = user.get("ydisk_token_enc", "")
        try:
            token = decrypt_str(token_enc)
        except Exception:
            token = ""

        if not token and not user.get("hide_disk_prompt"):
            prompt_text = (
                "📦 Вы ещё не подключили Яндекс.Диск!\n"
                "Подключите, чтобы сохранять PDF-документы и отчёты в облако."
                if lang == "RU"
                else "📦 You haven't connected Yandex.Disk yet!\nConnect it to store PDF reports in the cloud."
            )
            await message.answer(prompt_text, reply_markup=yandex_prompt_kb(lang))

@router.message(F.text == "← Главное меню")
async def back_to_main_menu(message: Message):
    """Возврат в главное меню"""
    first_name = message.from_user.first_name or ""
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?"
    )
    await message.answer(welcome, reply_markup=bottom_menu_kb(lang))

# --- Обработчики для английского языка ---
@router.message(F.text == "👤 Students")
async def msg_show_students_en(message: Message):
    """Показ списка учеников на английском"""
    from bot_app.handlers.students import _ensure_user, _no_students_text
    from bot_app.keyboards.main_menu import bottom_menu_students_kb
    
    await _ensure_user(message.from_user.id, message.from_user.first_name or "")
    from bot_app.database import db
    students = await db.get_students_by_user(message.from_user.id)
    text = _no_students_text() if not students else "Your students:"
    await message.answer(text, reply_markup=bottom_menu_students_kb(lang="EN"))

@router.message(F.text == "➕ Add Student")
async def msg_add_student_en(message: Message, state: FSMContext):
    """Добавление ученика на английском"""
    from bot_app.handlers.students import _ensure_user
    from bot_app.database import db
    
    user = message.from_user
    await _ensure_user(user.id, user.first_name or "")
    user_data = await db.get_user_by_tg_id(user.id)
    students = await db.get_students_by_user(user.id)

    if user_data and len(students) >= user_data.get("max_students", 3):
        await message.answer(
            "🚫 You have reached the limit of students.\n\n"
            "To add more, upgrade your plan in the «Subscription» section."
        )
        return

    from bot_app.handlers.students import AddStudentFSM
    await state.clear()
    await state.set_state(AddStudentFSM.name)
    await message.answer(
        "Enter student association (e.g., «7th grade girl», «physics boy»):"
    )

@router.message(F.text == "⚙️ Settings")
async def msg_settings_menu_en(message: Message):
    """Настройки на английском"""
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Profile Settings:" if lang == "EN" else "Настройки профиля:"
    from bot_app.keyboards.main_menu import bottom_menu_settings_kb
    await message.answer(text, reply_markup=bottom_menu_settings_kb(lang="EN"))

@router.message(F.text == "💳 Payment")
async def msg_subscription_en(message: Message):
    """Подписка на английском"""
    from bot_app.handlers.subscription import msg_subscription
    await msg_subscription(message, None)

# --- Обработчики для русского языка ---
@router.message(F.text == "👤 Ученики")
async def msg_show_students_ru(message: Message):
    """Показ списка учеников на русском"""
    from bot_app.handlers.students import msg_show_students
    await msg_show_students(message)

@router.message(F.text == "➕ Добавить ученика")
async def msg_add_student_ru(message: Message, state: FSMContext):
    """Добавление ученика на русском"""
    from bot_app.handlers.students import msg_add_student
    await msg_add_student(message, state)

@router.message(F.text == "⚙️ Настройки")
async def msg_settings_menu_ru(message: Message):
    """Настройки на русском"""
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    from bot_app.keyboards.main_menu import bottom_menu_settings_kb
    await message.answer(text, reply_markup=bottom_menu_settings_kb(lang="RU"))

@router.message(F.text == "💳 Подписка")
async def msg_subscription_ru(message: Message, state: FSMContext):
    """Подписка на русском"""
    from bot_app.handlers.subscription import msg_subscription
    await msg_subscription(message, state)
