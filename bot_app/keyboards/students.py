from aiogram.utils.keyboard import InlineKeyboardBuilder

def students_list_kb(students: list, lang: str = "RU"):
    """
    Build an inline keyboard listing all students.
    Each student's name is a button that opens that student's action menu.
    Includes 'Add new' and 'Back'.
    """
    kb = InlineKeyboardBuilder()
    for s in students:
        name = s["name"] or ("Без имени" if lang.upper() == "RU" else "No Name")
        kb.button(text=name, callback_data=f"student:{s['id']}")
    # "Add new" button
    add_text = "➕ Добавить нового" if lang.upper() == "RU" else "➕ Add new"
    kb.button(text=add_text, callback_data="add_student")
    # Back button to main menu
    back_text = "← Назад" if lang.upper() == "RU" else "← Back"
    kb.button(text=back_text, callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

from aiogram.types import InlineKeyboardMarkup

def student_actions_kb(student_id: int, lang: str = "RU") -> InlineKeyboardMarkup:
    """
    Inline keyboard for actions on a specific student: Open chat, Edit, Delete, Back.
    """
    kb = InlineKeyboardBuilder()
    
    if lang.upper() == "EN":
        kb.button(text="🔓 Open Chat", callback_data=f"open_chat:{student_id}")
        #kb.button(text="✏️ Edit Name", callback_data=f"edit_student:{student_id}")
        kb.button(text="🗑 Delete", callback_data=f"delete_student:{student_id}")
        kb.button(text="← Back", callback_data="back:students")
    else:
        kb.button(text="🔓 Открыть чат", callback_data=f"open_chat:{student_id}")
        kb.button(text="✏️ Изменить имя", callback_data=f"edit_student:{student_id}")
        #kb.button(text="🗑 Удалить ученика", callback_data=f"delete_student:{student_id}")
        kb.button(text="← Назад", callback_data="back:students")

    kb.adjust(1)
    return kb.as_markup()

def confirm_delete_kb(student_id: int, lang: str = "RU"):
    """
    Confirmation keyboard for deleting a student profile.
    """
    kb = InlineKeyboardBuilder()
    yes_text = "Да" if lang.upper() == "RU" else "Yes"
    no_text = "Нет" if lang.upper() == "RU" else "No"
    kb.button(text=yes_text, callback_data=f"confirm_delete:{student_id}:yes")
    kb.button(text=no_text, callback_data=f"confirm_delete:{student_id}:no")
    kb.adjust(2)
    return kb.as_markup()
