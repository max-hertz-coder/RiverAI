from aiogram.utils.keyboard import InlineKeyboardBuilder

def chat_menu_kb(student_id: int, lang: str = "RU"):
    """
    Inline keyboard for a student's chat context menu:
    Generate Plan, Generate Tasks, Check Homework, Chat with GPT, Back.
    """
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="📄 Generate Study Plan", callback_data=f"gen_plan:{student_id}")
        kb.button(text="📝 Generate Tasks", callback_data=f"gen_tasks:{student_id}")
        kb.button(text="✔️ Check Homework", callback_data=f"check_hw:{student_id}")
        kb.button(text="💬 Chat with GPT", callback_data=f"chat_gpt:{student_id}")
        kb.button(text="← Back", callback_data="back:students")
    else:
        kb.button(text="📄 Генерация учебного плана", callback_data=f"gen_plan:{student_id}")
        kb.button(text="📝 Генерация заданий", callback_data=f"gen_tasks:{student_id}")
        kb.button(text="✔️ Проверка ДЗ", callback_data=f"check_hw:{student_id}")
        kb.button(text="💬 Пообщаться с GPT", callback_data=f"chat_gpt:{student_id}")
        kb.button(text="← Назад", callback_data="back:students")
    kb.adjust(1)
    return kb.as_markup()

def result_plan_kb(student_id: int, lang: str = "RU"):
    """Inline keyboard after generating a plan: Correct, Save to Y.Disk, Back."""
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
    """Inline keyboard after generating tasks: Correct, Send to chat, Save PDF, Back."""
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
    """Inline keyboard after homework check: Correct, Save report, Back."""
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
    """Inline keyboard with just a Back button for GPT chat context (attached to each GPT answer)."""
    text = "← Back" if lang.upper() == "EN" else "← Назад"
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data="back:chat")
    return kb.as_markup()
