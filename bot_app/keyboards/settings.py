from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def settings_menu_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="← Back", callback_data="back:main")
    else:
        kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()


def yandex_prompt_kb(lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="🔗 Connect", callback_data="set_ydisk_token")
        kb.button(text="❌ Don't show again", callback_data="dismiss_disk_prompt")
    else:
        kb.button(text="🔗 Подключить диск", callback_data="set_ydisk_token")
        kb.button(text="❌ Не напоминать", callback_data="dismiss_disk_prompt")
    kb.adjust(2)
    return kb.as_markup()
