from aiogram.utils.keyboard import InlineKeyboardBuilder

# Main menu keyboard (language-specific labels will be provided as arguments)
def main_menu_kb(lang: str = "RU"):
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="👤 My Students", callback_data="show_students")
        kb.button(text="➕ Add Student", callback_data="add_student")
        kb.button(text="💳 Subscription", callback_data="subscription")
        kb.button(text="⚙️ Settings", callback_data="settings")
    else:  # default Russian
        kb.button(text="👤 Мои ученики", callback_data="show_students")
        kb.button(text="➕ Добавить ученика", callback_data="add_student")
        kb.button(text="💳 Подписка", callback_data="subscription")
        kb.button(text="⚙️ Настройки", callback_data="settings")
    kb.adjust(1)  # one button per row
    return kb.as_markup()

# Back button (used in various menus)
def back_button(text: str = "← Back", cb_data: str = "back:main"):
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=cb_data)
    return kb.as_markup()
