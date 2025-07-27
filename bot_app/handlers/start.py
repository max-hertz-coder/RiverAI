from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие и показ меню."""
    first_name = message.from_user.first_name or ""
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
    lang = "RU"  # можно подтягивать из БД, пока жёстко RU
    welcome = welcome_text_en if lang == "EN" else welcome_text_ru

    # Вступительный message с inline-кнопками
    await message.reply(welcome, reply_markup=main_menu_kb(lang))
    # Постоянная reply-клавиатура под полем ввода
    await message.answer("Выберите пункт меню:", reply_markup=bottom_menu_kb(lang))


from bot_app.keyboards.main_menu import main_menu_kb

@router.callback_query(F.data == "back:main")
async def cb_back_to_main(callback: CallbackQuery):
    first_name = callback.from_user.first_name or ""
    welcome = (
        f"🤖 ИИ-Ассистент для Репетитора\n"
        f"Добро пожаловать, {first_name}!\n"
        f"Чем займёмся сегодня?"
    )
    await callback.message.edit_text(
        welcome,
        reply_markup=main_menu_kb("RU")
    )