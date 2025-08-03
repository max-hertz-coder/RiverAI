from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram import F

from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb
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

    # 1. Inline-меню
    await message.reply(welcome, reply_markup=main_menu_kb(lang))

    # 2. Reply-меню (под строкой ввода)
    await message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb(lang))

    # 3. Предложение подключить Яндекс.Диск
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


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показ справки."""
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user and "language" in user else "RU"
    
    help_text = (
        "🤖 **AI Assistant for Tutors - Help**\n\n"
        "**Available commands:**\n"
        "• /start - Start the bot and show main menu\n"
        "• /help - Show this help message\n\n"
        "**Main features:**\n"
        "• 📚 Generate study plans and tasks\n"
        "• 📝 Check homework assignments\n"
        "• 💬 Chat with AI assistant\n"
        "• 👥 Manage students\n"
        "• ⚙️ Configure settings\n\n"
        "**How to use:**\n"
        "1. Add students in the Students section\n"
        "2. Generate study plans and tasks\n"
        "3. Check homework using photo upload\n"
        "4. Chat with AI for additional help\n\n"
        "For more information, use the main menu buttons."
        if lang == "EN"
        else "🤖 **ИИ-Ассистент для Репетитора - Справка**\n\n"
        "**Доступные команды:**\n"
        "• /start - Запустить бота и показать главное меню\n"
        "• /help - Показать эту справку\n\n"
        "**Основные возможности:**\n"
        "• 📚 Генерация планов обучения и заданий\n"
        "• 📝 Проверка домашних заданий\n"
        "• 💬 Чат с ИИ-ассистентом\n"
        "• 👥 Управление учениками\n"
        "• ⚙️ Настройки\n\n"
        "**Как использовать:**\n"
        "1. Добавьте учеников в разделе Ученики\n"
        "2. Генерируйте планы обучения и задания\n"
        "3. Проверяйте домашние задания через загрузку фото\n"
        "4. Общайтесь с ИИ для дополнительной помощи\n\n"
        "Для получения дополнительной информации используйте кнопки главного меню."
    )
    
    await message.reply(help_text, parse_mode="Markdown")


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
