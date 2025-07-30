# bot_app/keyboards/main_menu.py

from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

def main_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="👤 My Students",   callback_data="show_students")
        kb.button(text="➕ Add Student",   callback_data="add_student")
        kb.button(text="💳 Subscription",  callback_data="subscription")
        kb.button(text="⚙️ Settings",     callback_data="settings")
    else:
        kb.button(text="👤 Мои ученики",     callback_data="show_students")
        kb.button(text="➕ Добавить ученика", callback_data="add_student")
        kb.button(text="💳 Подписка",        callback_data="subscription")
        kb.button(text="⚙️ Настройки",       callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def bottom_menu_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    labels = (
        ["👤 Students", "➕ Add Student", "⚙️ Settings", "💳 Payment"]
        if lang.upper() == "EN"
        else ["👤 Ученики", "➕ Добавить ученика", "⚙️ Настройки", "💳 Подписка"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(1)
    return rb.as_markup(resize_keyboard=True)
