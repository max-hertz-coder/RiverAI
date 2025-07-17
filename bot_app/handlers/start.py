from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle the /start command: greet user and show main menu."""
    first_name = message.from_user.first_name or ""
    # Тексты приветствия
    welcome_text_ru = (
        f"🤖 ИИ-Ассистент для Репетитора\n"
        f"Добро пожаловать, {first_name}!\n"
        f"Чем займёмся сегодня?"
    )
    welcome_text_en = (
        f"🤖 AI Assistant for Tutors\n"
        f"Welcome, {first_name}!\n"
        f"What shall we do today?"
    )
    # По умолчанию RU (или можно получить из БД)
    lang = "RU"
    welcome_text = welcome_text_en if lang == "EN" else welcome_text_ru

    # Inline-клавиатура в сообщении
    await message.reply(welcome_text, reply_markup=main_menu_kb(lang))
    # Постоянная reply-клавиатура под полем ввода
    await message.answer(
        "Выберите пункт меню:",
        reply_markup=bottom_menu_kb(lang)
    )
