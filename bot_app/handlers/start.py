# bot_app/handlers/start.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
import os

from bot_app.keyboards.main_menu import main_menu_kb, bottom_menu_kb

router = Router()


def _agree_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data="accept_policy"),
            InlineKeyboardButton(text="Нет", callback_data="reject_policy"),
        ]
    ])


def _yes_no_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=yes_cb),
            InlineKeyboardButton(text="Нет", callback_data=no_cb),
        ]
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    /start:
    1) Показываем два файла (соглашение и политику) + кнопки Да/Нет.
    2) При "Да" – спрашиваем про просмотр инструкций.
    """
    # Пытаемся отправить 2 файла (если они есть в рабочем каталоге)
    policy_path = "policy.pdf"
    privacy_path = "privacy.pdf"

    sent_any = False
    if os.path.exists(policy_path):
        await message.answer_document(FSInputFile(policy_path), caption="")
        sent_any = True
    if os.path.exists(privacy_path):
        await message.answer_document(FSInputFile(privacy_path), caption="")
        sent_any = True

    if not sent_any:
        await message.answer(
            "Пожалуйста, ознакомьтесь с политикой конфиденциальности и соглашением об обработке персональных данных."
        )

    await message.answer(
        "При нажатии «Да» вы подтверждаете, что ознакомились с документами и принимаете их условия.",
        reply_markup=_agree_kb(),
    )


@router.callback_query(F.data == "accept_policy")
async def cb_accept_policy(callback: CallbackQuery):
    """Пользователь принял соглашение: предлагаем видео-инструкции."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        "Отлично! Мы подготовили видео-инструкции по пользованию ботом, чтобы раскрыть потенциал его функционала. Хотите ли вы с ними ознакомиться?",
        reply_markup=_yes_no_kb("start_tutorial", "skip_tutorial"),
    )
    await callback.answer()


@router.callback_query(F.data == "reject_policy")
async def cb_reject_policy(callback: CallbackQuery):
    """Отказ — показываем предупреждение."""
    await callback.answer("Чтобы пользоваться ботом, необходимо принять условия.", show_alert=True)


@router.callback_query(F.data == "start_tutorial")
async def cb_start_tutorial(callback: CallbackQuery):
    """
    Начинаем показ видеороликов. Структура:
    1) Генерация материала → «Да ✅»
    2) Проверка ДЗ → «Да ✅»
    3) Ведение досье → «Да ✅»
    4) Чат с GPT → «Да ✅» → главный экран
    """
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _send_tutorial_video(callback, step=1)
    await callback.answer()


@router.callback_query(F.data == "skip_tutorial")
async def cb_skip_tutorial(callback: CallbackQuery):
    """Пропустили инструкции — на главный экран."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    first_name = callback.from_user.first_name or ""
    await callback.message.answer(
        f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?",
        reply_markup=main_menu_kb("RU"),
    )
    await callback.message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb("RU"))
    await callback.answer()


@router.callback_query(F.data.startswith("tutorial:"))
async def cb_tutorial_step(callback: CallbackQuery):
    """Переход по шагам «Да ✅»."""
    try:
        step = int(callback.data.split(":", 1)[1])
    except Exception:
        return await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if step in (1, 2, 3):
        await _send_tutorial_video(callback, step=step + 1)
    else:
        # Закончились ролики — на главный экран.
        first_name = callback.from_user.first_name or ""
        await callback.message.answer(
            f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?",
            reply_markup=main_menu_kb("RU"),
        )
        await callback.message.answer("⬇ Меню под полем ввода:", reply_markup=bottom_menu_kb("RU"))
    await callback.answer()


async def _send_tutorial_video(callback: CallbackQuery, step: int):
    """
    Отправляет видео для текущего шага и рисует кнопку «Да ✅».
    step = 1..4
    """
    captions = {
        1: "Отлично, ознакомьтесь с инструкцией использования функции «Генерация материала».",
        2: "Инструкция использования функции «Проверка ДЗ».",
        3: "Инструкция использования функции «Ведение досье».",
        4: "Инструкция использования функции «Чат с GPT».",
    }
    files = {
        1: "instruction_generation.mp4",
        2: "instruction_homework.mp4",
        3: "instruction_dossier.mp4",
        4: "instruction_chat.mp4",
    }

    btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да ✅", callback_data=f"tutorial:{step}")]
    ])

    file_path = files.get(step)
    if file_path and os.path.exists(file_path):
        await callback.message.answer_video(FSInputFile(file_path), caption=captions.get(step, ""), reply_markup=btn)
    else:
        # Если файла нет — шлём заглушку
        await callback.message.answer(f"{captions.get(step, 'Инструкция')}\n(Видео пока не загружено)", reply_markup=btn)
