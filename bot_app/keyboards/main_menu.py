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

def back_button(text: str = "← Назад", cb_data: str = "back:main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=cb_data)
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

def bottom_menu_students_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    """Нижнее меню для работы с учениками"""
    labels = (
        ["👤 Students", "📄 Generate Plan", "📝 Generate Tasks", "✅ Check HW", "💬 Chat GPT", "← Back to Main"]
        if lang.upper() == "EN"
        else ["👤 Ученики", "📄 Учебный план", "📝 Задания", "✅ Проверить ДЗ", "💬 Чат с GPT", "← Главное меню"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(2)  # две кнопки в ряд
    return rb.as_markup(resize_keyboard=True)

def bottom_menu_student_actions_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    """Нижнее меню для действий с конкретным учеником"""
    labels = (
        ["📄 Generate Plan", "📝 Generate Tasks", "✅ Check HW", "💬 Chat GPT", "🗑 Delete Student", "← Back to Students"]
        if lang.upper() == "EN"
        else ["📄 Учебный план", "📝 Задания", "✅ Проверить ДЗ", "💬 Чат с GPT", "🗑 Удалить ученика", "← К ученикам"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(2)  # две кнопки в ряд
    return rb.as_markup(resize_keyboard=True)

def bottom_menu_generation_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    """Нижнее меню для генерации контента"""
    labels = (
        ["📄 Generate Plan", "📝 Generate Tasks", "✅ Check HW", "💬 Chat GPT", "← Back to Students"]
        if lang.upper() == "EN"
        else ["📄 Учебный план", "📝 Задания", "✅ Проверить ДЗ", "💬 Чат с GPT", "← К ученикам"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(2)  # две кнопки в ряд
    return rb.as_markup(resize_keyboard=True)

def bottom_menu_settings_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    """Нижнее меню для настроек"""
    labels = (
        ["🔗 Connect Yandex.Disk", "✏️ Edit Yandex.Disk Token", "← Back to Main"]
        if lang.upper() == "EN"
        else ["🔗 Подключить Яндекс.Диск", "✏️ Изменить токен Я.Диска", "← Главное меню"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(1)
    return rb.as_markup(resize_keyboard=True)

def bottom_menu_subscription_kb(lang: str = "RU") -> ReplyKeyboardMarkup:
    """Нижнее меню для подписки"""
    labels = (
        ["💳 Change Plan", "💳 Renew Subscription", "📊 Payment History", "← Back to Main"]
        if lang.upper() == "EN"
        else ["💳 Изменить тариф", "💳 Продлить подписку", "📊 История платежей", "← Главное меню"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(1)
    return rb.as_markup(resize_keyboard=True)
