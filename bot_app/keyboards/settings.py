from aiogram.utils.keyboard import InlineKeyboardBuilder

def settings_menu_kb(lang: str = "RU"):
    """
    Inline keyboard for Settings menu: Change name, Change password, Notifications, Change language, Yandex Disk, Back.
    """
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="🔤 Change Name", callback_data="change_name")
        kb.button(text="🔑 Change Password", callback_data="change_password")
        kb.button(text="🔔 Toggle Notifications", callback_data="toggle_notifications")
        kb.button(text="🌐 Change Language", callback_data="change_language")
        kb.button(text="🗄️ Yandex Disk Integration", callback_data="yandex_disk")
        kb.button(text="← Back", callback_data="back:main")
    else:
        kb.button(text="🔤 Изменить имя", callback_data="change_name")
        kb.button(text="🔑 Изменить пароль", callback_data="change_password")
        kb.button(text="🔔 Уведомления", callback_data="toggle_notifications")
        kb.button(text="🌐 Сменить язык", callback_data="change_language")
        kb.button(text="🗄️ Яндекс.Диск", callback_data="yandex_disk")
        kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def language_choice_kb():
    """Inline keyboard for choosing language (RU/EN)."""
    kb = InlineKeyboardBuilder()
    kb.button(text="RU 🇷🇺", callback_data="lang:RU")
    kb.button(text="EN 🇺🇸", callback_data="lang:EN")
    kb.adjust(2)
    return kb.as_markup()
