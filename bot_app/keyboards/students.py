from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def students_list_kb(students: list, lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in students:
        name = s.get("name") or ("Без имени" if lang.upper() == "RU" else "No Name")
        kb.button(text=name, callback_data=f"student:{s['id']}")
    kb.button(
        text="➕ Добавить нового" if lang.upper() == "RU" else "➕ Add new",
        callback_data="add_student",
    )
    kb.button(
        text="← Назад" if lang.upper() == "RU" else "← Back",
        callback_data="back:main",
    )
    kb.adjust(1)
    return kb.as_markup()


def student_actions_kb(student_id: int, lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(text="📄 Generate tasks", callback_data=f"generate_tasks:{student_id}")
        kb.button(text="✅ Check homework", callback_data=f"check_homework:{student_id}")
        kb.button(text="💬 Chat with GPT", callback_data=f"chat_gpt:{student_id}")
        kb.button(text="🗑 Delete student", callback_data=f"delete_student:{student_id}")
        kb.button(text="← Back", callback_data="back:students")
    else:
        kb.button(text="📄 Генерировать задания", callback_data=f"generate_tasks:{student_id}")
        kb.button(text="✅ Проверка ДЗ", callback_data=f"check_homework:{student_id}")
        kb.button(text="💬 Чат с GPT", callback_data=f"chat_gpt:{student_id}")
        kb.button(text="🗑 Удалить ученика", callback_data=f"delete_student:{student_id}")
        kb.button(text="← Назад", callback_data="back:students")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_kb(student_id: int, lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    yes_text = "Да" if lang.upper() == "RU" else "Yes"
    no_text = "Нет" if lang.upper() == "RU" else "No"
    kb.button(text=yes_text, callback_data=f"confirm_delete:{student_id}:yes")
    kb.button(text=no_text, callback_data=f"confirm_delete:{student_id}:no")
    kb.adjust(2)
    return kb.as_markup()


def back_button(text: str = "← Назад", callback: str = "back:main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=callback)
    kb.adjust(1)
    return kb.as_markup()
