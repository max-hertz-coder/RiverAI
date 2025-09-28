# bot_app/keyboards/main_menu.py
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

SUPPORT_URL = "https://t.me/mx_hertz"

def main_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="👤 Students", callback_data="show_students")
        kb.button(text="💳 Subscription", callback_data="subscription")
        kb.button(text="ℹ️ Instructions", callback_data="instructions:open")
        kb.button(text="🆘 Support", url=SUPPORT_URL)
    else:
        kb.button(text="👤 Ученики", callback_data="show_students")
        kb.button(text="💳 Подписка", callback_data="subscription")
        kb.button(text="ℹ️ Инструкции", callback_data="instructions:open")
        kb.button(text="🆘 Поддержка", url=SUPPORT_URL)
    kb.adjust(1)
    return kb.as_markup()

def back_button(text: str = "← Назад", cb_data: str = "back:main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=cb_data)
    kb.adjust(1)
    return kb.as_markup()

def bottom_menu_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    labels = (
        ["👤 Students", "💳 Subscription", "ℹ️ Instructions", "🆘 Support"]
        if lang.upper() == "EN"
        else ["👤 Ученики", "💳 Подписка", "ℹ️ Инструкции", "🆘 Поддержка"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(1)
    return rb.as_markup(resize_keyboard=True)
