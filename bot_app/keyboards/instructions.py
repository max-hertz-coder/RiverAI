# bot_app/keyboards/instructions.py
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

def instructions_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Генерация материала", callback_data="instructions:gen_material")
    kb.button(text="✅ Проверка ДЗ", callback_data="instructions:check_hw")
    kb.button(text="📁 Ведение досье", callback_data="instructions:dossier")
    kb.button(text="💬 Чат с GPT", callback_data="instructions:chat_gpt")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def after_video_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data="instructions:more_yes")
    kb.button(text="Нет", callback_data="instructions:more_no")
    kb.adjust(2)
    return kb.as_markup()
