# bot_app/handlers/instructions.py
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from bot_app.keyboards.instructions import instructions_menu_kb, after_video_kb
from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb

router = Router()

# ===== ВХОД В РАЗДЕЛ «ИНСТРУКЦИИ» =====

@router.callback_query(F.data == "instructions:open")
async def open_instructions_cb(cb: CallbackQuery):
    await cb.message.answer(
        "Инструкция по какому конкретно функционалу вас интересует?",
        reply_markup=instructions_menu_kb()
    )
    await cb.answer()

# Если нажали кнопку из reply-клавиатуры (нижнее меню)
@router.message(F.text == "ℹ️ Инструкции")
async def open_instructions_msg(msg: Message):
    await msg.answer(
        "Инструкция по какому конкретно функционалу вас интересует?",
        reply_markup=instructions_menu_kb()
    )

# ===== ОТПРАВКА КОНКРЕТНЫХ ВИДЕО =====

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

async def _send_instruction(target: Message | CallbackQuery, key: str):
    caption, file_name = _FILES[key]
    if isinstance(target, CallbackQuery):
        m = target.message
    else:
        m = target
    if file_name and os.path.exists(file_name):
        await m.answer_video(FSInputFile(file_name), caption=caption, reply_markup=after_video_kb())
    else:
        await m.answer(f"{caption}\n(Видео пока не загружено)", reply_markup=after_video_kb())

@router.callback_query(F.data == "instructions:gen_material")
async def inst_gen(cb: CallbackQuery):
    await _send_instruction(cb, "gen_material"); await cb.answer()

@router.callback_query(F.data == "instructions:check_hw")
async def inst_hw(cb: CallbackQuery):
    await _send_instruction(cb, "check_hw"); await cb.answer()

@router.callback_query(F.data == "instructions:dossier")
async def inst_dossier(cb: CallbackQuery):
    await _send_instruction(cb, "dossier"); await cb.answer()

@router.callback_query(F.data == "instructions:chat_gpt")
async def inst_chat(cb: CallbackQuery):
    await _send_instruction(cb, "chat_gpt"); await cb.answer()

# ===== «Остались вопросы?» — Да/Нет =====

@router.callback_query(F.data == "instructions:more_yes")
async def more_yes(cb: CallbackQuery):
    await cb.message.answer(
        "Инструкция по какому конкретно функционалу вас интересует?",
        reply_markup=instructions_menu_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "instructions:more_no")
async def more_no(cb: CallbackQuery):
    first_name = cb.from_user.first_name or ""
    await cb.message.answer(
        f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?",
        reply_markup=main_menu_kb("RU"),
    )
    await cb.message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb("RU"))
    await cb.answer()

# ===== Поддержка из reply-клавиатуры =====
@router.message(F.text == "🆘 Поддержка")
async def support_msg(msg: Message):
    await msg.answer("Связаться с поддержкой: @mx_hertz\nhttps://t.me/mx_hertz")

# На случай возврата «Назад»
@router.callback_query(F.data == "back:main")
async def back_main(cb: CallbackQuery):
    first_name = cb.from_user.first_name or ""
    await cb.message.answer(
        f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?",
        reply_markup=main_menu_kb("RU"),
    )
    await cb.message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb("RU"))
    await cb.answer()
