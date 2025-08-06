# bot_app/keyboards/main_menu.py

from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

def main_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="📚 Generate Tasks", callback_data="generate_tasks")
        kb.button(text="📝 Check Homework", callback_data="check_homework")
        kb.button(text="💬 Chat with GPT", callback_data="chat_gpt")
        kb.button(text="💳 Subscription", callback_data="subscription")
        kb.button(text="⚙️ Settings", callback_data="settings")
    else:
        kb.button(text="📚 Генерировать задания", callback_data="generate_tasks")
        kb.button(text="📝 Проверить ДЗ", callback_data="check_homework")
        kb.button(text="💬 Чат с GPT", callback_data="chat_gpt")
        kb.button(text="💳 Подписка", callback_data="subscription")
        kb.button(text="⚙️ Настройки", callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def back_button(text: str = "← Назад", cb_data: str = "back:main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=cb_data)
    kb.adjust(1)
    return kb.as_markup()

def bottom_menu_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    labels = (
        ["📚 Generate Tasks", "📝 Check Homework", "💬 Chat with GPT", "⚙️ Settings", "💳 Payment"]
        if lang.upper() == "EN"
        else ["📚 Генерировать задания", "📝 Проверить ДЗ", "💬 Чат с GPT", "⚙️ Настройки", "💳 Подписка"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(1)
    return rb.as_markup(resize_keyboard=True)
