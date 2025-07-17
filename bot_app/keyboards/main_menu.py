# bot_app/keyboards/main_menu.py

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_kb(lang: str = "RU"):
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="👤 My Students",    callback_data="show_students")
        kb.button(text="➕ Add Student",    callback_data="add_student")
        kb.button(text="💳 Subscription",   callback_data="subscription")
        kb.button(text="⚙️ Settings",      callback_data="settings")
    else:
        kb.button(text="👤 Мои ученики",     callback_data="show_students")
        kb.button(text="➕ Добавить ученика", callback_data="add_student")
        kb.button(text="💳 Подписка",        callback_data="subscription")
        kb.button(text="⚙️ Настройки",       callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def bottom_menu_kb(lang: str = "RU"):
    # labels для reply-клавиатуры
    if lang.upper() == "EN":
        labels = ["👤 Students", "➕ Add Student", "⚙️ Settings", "💳 Payment"]
    else:
        labels = ["👤 Ученики", "➕ Добавить ученика", "⚙️ Настройки", "💳 Оплата"]

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for label in labels:
        kb.add(KeyboardButton(text=label))
    return kb
