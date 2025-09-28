# bot_app/handlers/instructions.py
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from bot_app.keyboards.instructions import instructions_menu_kb, after_video_kb
from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb

router = Router()

# --- Вход в раздел «Инструкции» ---

@router.callback_query(F.data == "instructions:open")
async def open_instructions(cb: CallbackQuery):
    await cb.message.edit_text(
        "Инструкция по какому конкретно функционалу вас интересует?",
        reply_markup=instructions_menu_kb()
    )
    await cb.answer()

# Для reply-клавиатуры (если нажали текст «ℹ️ Инструкции»)
@router.message(F.text == "ℹ️ Инструкции")
async def msg_open_instructions(msg: Message):
    await msg.answer(
        "Инструкция по какому конкретно функционалу вас интересует?",
        reply_markup=instructions_menu_kb()
    )

# --- Отправка конкретных видео ---

_FILES = {
    "gen_material": ("Отлично, ознакомьтесь с инструкцией использования функции «Генерация материала».",
                     "instruction_generation.mp4"),
    "check_hw":     ("Инструкция использования функции «Проверка ДЗ».",
                     "instruction_homework.mp4"),
    "dossier":      ("Инструкция использования функции «Ведение досье».",
                     "instruction_dossier.mp4"),
    "chat_gpt":     ("Инструкция использования функции «Чат с GPT».",
                     "instruction_chat.mp4"),
}

async def _send_instruction(cb_or_msg, key: str):
    caption, file_name = _FILES[key]
    if isinstance(cb_or_msg, CallbackQuery):
        target = cb_or_msg.message
    else:
        target = cb_or_msg

    if file_name and os.path.exists(file_name):
        await target.answer_video(FSInputFile(file_name), caption=caption, reply_markup=after_video_kb())
    else:
        await target.answer(f"{caption}\n(Видео пока не загружено)", reply_markup=after_video_kb())

@router.callback_query(F.data == "instructions:gen_material")
async def i_gen(cb: CallbackQuery):
    await _send_instruction(cb, "gen_material")
    await cb.answer()

@router.callback_query(F.data == "instructions:check_hw")
async def i_hw(cb: CallbackQuery):
    await _send_instruction(cb, "check_hw")
    await cb.answer()

@router.callback_query(F.data == "instructions:dossier")
async def i_dossier(cb: CallbackQuery):
    await _send_instruction(cb, "dossier")
    await cb.answer()

@router.callback_query(F.data == "instructions:chat_gpt")
async def i_chat(cb: CallbackQuery):
    await _send_instruction(cb, "chat_gpt")
    await cb.answer()

# --- «Остались вопросы?» Да/Нет ---

@router.callback_query(F.data == "instructions:more_yes")
async def more_yes(cb: CallbackQuery):
    # Возвращаем меню разделов
    await cb.message.answer(
        "Инструкция по какому конкретно функционалу вас интересует?",
        reply_markup=instructions_menu_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "instructions:more_no")
async def more_no(cb: CallbackQuery):
    # На главный экран
    first_name = cb.from_user.first_name or ""
    await cb.message.answer(
        f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?",
        reply_markup=main_menu_kb("RU"),
    )
    await cb.message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb("RU"))
    await cb.answer()

# --- Поддержка ---

@router.message(F.text == "🆘 Поддержка")
async def msg_support(msg: Message):
    await msg.answer("Связаться с поддержкой: @mx_hertz\nhttps://t.me/mx_hertz")

# На случай, если где-то используется callback «back:main»
@router.callback_query(F.data == "back:main")
async def back_main(cb: CallbackQuery):
    first_name = cb.from_user.first_name or ""
    await cb.message.edit_text(
        f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?",
        reply_markup=main_menu_kb("RU"),
    )
    await cb.message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb("RU"))
    await cb.answer()
