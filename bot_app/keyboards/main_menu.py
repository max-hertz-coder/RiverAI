# bot_app/keyboards/main_menu.py

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

def main_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    """
    Inline-клавиатура главного меню.
    """
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

def back_button(text: str = "← Назад", cb_data: str = "back:main") -> InlineKeyboardMarkup:
    """
    Inline-кнопка «Назад» для возврата к предыдущему меню.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=cb_data)
    kb.adjust(1)
    return kb.as_markup()

def bottom_menu_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    """
    Постоянная reply-клавиатура под полем ввода.
    """
    if lang.upper() == "EN":
        labels = ["👤 Students", "➕ Add Student", "⚙️ Settings", "💳 Payment"]
    else:
        labels = ["👤 Ученики", "➕ Добавить ученика", "⚙️ Настройки", "💳 Оплата"]

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for label in labels:
        kb.add(KeyboardButton(text=label))
    return kb
