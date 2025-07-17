from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

def main_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="👤 My Students", callback_data="show_students")
        kb.button(text="➕ Add Student", callback_data="add_student")
        kb.button(text="💳 Subscription", callback_data="subscription")
        kb.button(text="⚙️ Settings", callback_data="settings")
    else:
        kb.button(text="👤 Мои ученики",     callback_data="show_students")
        kb.button(text="➕ Добавить ученика", callback_data="add_student")
        kb.button(text="💳 Подписка",        callback_data="subscription")
        kb.button(text="⚙️ Настройки",       callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def back_button(text: str = "← Назад", cb_data: str = "back:main") -> InlineKeyboardMarkup:
    """
    Inline-кнопка «Назад» для возврата к главному меню или предыдущему состоянию.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=cb_data)
    kb.adjust(1)
    return kb.as_markup()
