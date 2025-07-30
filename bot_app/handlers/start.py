from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram import F

from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb
from bot_app.keyboards.settings import yandex_prompt_kb
from bot_app import database

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

    # 1. Inline-меню
    await message.reply(welcome, reply_markup=main_menu_kb(lang))

    # 2. Reply-меню (под строкой ввода)
    await message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb(lang))

    # 3. Предложение подключить Яндекс.Диск
    if user and not user.get("yandex_token") and not user.get("hide_disk_prompt"):
        prompt_text = (
            "📦 Вы ещё не подключили Яндекс.Диск!\n"
            "Подключите, чтобы сохранять PDF-документы и отчёты в облако."
            if lang == "RU"
            else "📦 You haven't connected Yandex.Disk yet!\nConnect it to store PDF reports in the cloud."
        )
        await message.answer(prompt_text, reply_markup=yandex_prompt_kb(lang))


@router.callback_query(F.data == "back:main")
async def cb_back_to_main(callback: CallbackQuery):
    first_name = callback.from_user.first_name or ""
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    lang = user["language"] if user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня!"
    )
    await callback.message.edit_text(welcome, reply_markup=main_menu_kb(lang))
