from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def chat_menu_kb(student_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Задания", callback_data=f"generate_tasks:{student_id}")
    kb.button(text="🔄 Проверить ДЗ", callback_data=f"check_homework:{student_id}")
    kb.button(text="💬 Чат с GPT", callback_data=f"chat_gpt:{student_id}")
    kb.adjust(2)  # две кнопки в ряд и третья ниже
    return kb.as_markup()


def back_button(text: str = "← Назад", callback_data: str = "back:main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=callback_data)
    kb.adjust(1)
    return kb.as_markup()


def result_plan_kb(student_id: int, lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✏️ Исправить" if lang.upper() == "RU" else "✏️ Refine",
        callback_data=f"refine_plan:{student_id}",
    )
    kb.button(text="← Назад", callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()


def result_tasks_kb(student_id: int | None = None, lang: str = "RU") -> InlineKeyboardMarkup:
    """
    Клавиатура под результат генерации заданий.
    По проектной логике «исправить» без явного student_id — контекст берём из Redis.
    """
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✏️ Исправить" if lang.upper() == "RU" else "✏️ Refine",
        callback_data="refine_tasks",
    )
    kb.button(text="← Назад", callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()


def result_check_kb(student_id: int | None = None, lang: str = "RU") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✏️ Исправить проверку" if lang.upper() == "RU" else "✏️ Refine Check",
        callback_data=f"refine_check:{student_id or 0}",
    )
    kb.button(text="← Назад", callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()


def chat_gpt_back_kb(student_id: int | None = None, lang: str = "RU") -> InlineKeyboardMarkup:
    """
    Совместима с вызовами из result-consumer: параметр student_id опционален.
    Возвращаемся в меню чата (если состояние известно) или в главное меню.
    """
    text = "← Back" if lang.upper() == "EN" else "← Назад"
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data="back:chat")
    kb.adjust(1)
    return kb.as_markup()
