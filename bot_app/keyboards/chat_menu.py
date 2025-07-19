from aiogram.utils.keyboard import InlineKeyboardBuilder

# bot_app/keyboards/chat_menu.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# bot_app/keyboards/chat_menu.py
from aiogram.utils.keyboard import InlineKeyboardBuilder

def chat_menu_kb(student_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Учебный план",     callback_data=f"generate_plan:{student_id}")
    kb.button(text="📝 Задания",           callback_data=f"generate_tasks:{student_id}")
    kb.button(text="🔄 Проверить ДЗ",      callback_data=f"correct_tasks:{student_id}")
    kb.button(text="💬 Чат с GPT",         callback_data=f"chat_gpt:{student_id}")
    kb.adjust(2)  # две кнопки в ряд
    return kb.as_markup()


def back_button():
    kb = InlineKeyboardBuilder()
    kb.button(text="← Назад", callback_data="back")
    return kb.as_markup()

def result_plan_kb(student_id: int, lang: str = "RU"):
    """Keyboard after generating a plan: refine or save, back to menu."""
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="✏️ Refine", callback_data=f"refine_plan:{student_id}")
        kb.button(text="💾 Save to Y.Disk", callback_data=f"save_plan:{student_id}")
        kb.button(text="← Back", callback_data="back:chat")
    else:
        kb.button(text="✏️ Исправить", callback_data=f"refine_plan:{student_id}")
        kb.button(text="💾 Сохранить на Я.Диск", callback_data=f"save_plan:{student_id}")
        kb.button(text="← Назад", callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()

def result_tasks_kb(student_id: int, lang: str = "RU"):
    """Keyboard after generating tasks: refine, send to chat, save PDF, back."""
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="✏️ Refine", callback_data=f"refine_tasks:{student_id}")
        kb.button(text="➡️ Send to Chat", callback_data=f"send_tasks:{student_id}")
        kb.button(text="💾 Save PDF to Y.Disk", callback_data=f"save_tasks:{student_id}")
        kb.button(text="← Back", callback_data="back:chat")
    else:
        kb.button(text="✏️ Исправить", callback_data=f"refine_tasks:{student_id}")
        kb.button(text="➡️ Отправить в чат", callback_data=f"send_tasks:{student_id}")
        kb.button(text="💾 Сохранить PDF на Я.Диск", callback_data=f"save_tasks:{student_id}")
        kb.button(text="← Назад", callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()

def result_check_kb(student_id: int, lang: str = "RU"):
    """Keyboard after homework check: refine, save report, back."""
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="✏️ Refine Check", callback_data=f"refine_check:{student_id}")
        kb.button(text="💾 Save Report to Y.Disk", callback_data=f"save_check:{student_id}")
        kb.button(text="← Back", callback_data="back:chat")
    else:
        kb.button(text="✏️ Исправить проверку", callback_data=f"refine_check:{student_id}")
        kb.button(text="💾 Сохранить отчёт на Я.Диск", callback_data=f"save_check:{student_id}")
        kb.button(text="← Назад", callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()

def chat_gpt_back_kb(lang: str = "RU"):
    """Keyboard with a Back button for GPT chat context."""
    text = "← Back" if lang.upper() == "EN" else "← Назад"
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data="back:chat")
    return kb.as_markup()
