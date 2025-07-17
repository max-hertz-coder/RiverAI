from aiogram import Router, Bot
from aiogram.types import Message

from bot_app.keyboards.main_menu import main_menu_kb

router = Router()

from aiogram.filters import Command

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle the /start command: greet user and show main menu."""
    user_id = message.from_user.id
    # We assume AuthMiddleware already created the user in DB if not exists.
    # Send welcome message
    welcome_text_ru = (f"🤖 ИИ-Ассистент для Репетитора\n"
                       f"Добро пожаловать, {message.from_user.first_name}!\n"
                       f"Чем займёмся сегодня?")
    welcome_text_en = (f"🤖 AI Assistant for Tutors\n"
                       f"Welcome, {message.from_user.first_name}!\n"
                       f"What shall we do today?")
    # Determine language preference (could fetch from DB if we had it in context, but we'll default to RU for /start)
    # If a user record exists with language setting, it should be loaded; for simplicity, default to RU on first start.
    lang = "RU"
    # If we had user language from DB, we could incorporate it here.

    welcome_text = welcome_text_en if lang == "EN" else welcome_text_ru
    await message.reply(welcome_text, reply_markup=main_menu_kb(lang))
