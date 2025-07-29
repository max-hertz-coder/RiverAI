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

from aiogram.utils.keyboard import InlineKeyboardBuilder

def student_actions_kb(student_id: int, lang: str = "RU"):
    """
    Клавиатура действий с учеником: только генерация заданий и удаление.
    """
    kb = InlineKeyboardBuilder()
    if lang.upper() == "EN":
        kb.button(
            text="📄 Generate tasks",
            callback_data=f"generate_tasks:{student_id}"
        )
        kb.button(
            text="🗑 Delete student",
            callback_data=f"delete_student:{student_id}"
        )
    else:
        kb.button(
            text="📄 Генерировать задания",
            callback_data=f"generate_tasks:{student_id}"
        )
        kb.button(
            text="🗑 Удалить ученика",
            callback_data=f"delete_student:{student_id}"
        )
    # один столбец, по одной кнопке на строку
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
