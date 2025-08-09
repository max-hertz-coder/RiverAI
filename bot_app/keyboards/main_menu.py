from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    """
    Главное меню. Без прямых действий генерации/чата (они требуют student_id),
    поэтому даём вход в список учеников + разделы подписки/настроек.
    """
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="👤 Students", callback_data="show_students")
        kb.button(text="💳 Subscription", callback_data="subscription")
        kb.button(text="⚙️ Settings", callback_data="settings")
    else:
        kb.button(text="👤 Ученики", callback_data="show_students")
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
    """
    Кнопки снизу (reply-клавиатура). Можно оставить как быстрый доступ.
    """
    labels = (
        ["👤 Students", "💳 Subscription", "⚙️ Settings"]
        if lang.upper() == "EN"
        else ["👤 Ученики", "💳 Подписка", "⚙️ Настройки"]
    )
    rb = ReplyKeyboardBuilder()
    for label in labels:
        rb.button(text=label)
    rb.adjust(1)
    return rb.as_markup(resize_keyboard=True)
