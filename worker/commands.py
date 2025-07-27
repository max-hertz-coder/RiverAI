from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from .tasks_module import handle_generate, handle_check, handle_chat, handle_plan

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("/generate_tasks")],
        [KeyboardButton("/check_homework"), KeyboardButton("/talk_with_gpt")],
        [KeyboardButton("/create_plan")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

def register_handlers(dp):
    dp.message.register(cmd_generate, Command("generate_tasks"))
    dp.message.register(cmd_check, Command("check_homework"))
    dp.message.register(cmd_talk, Command("talk_with_gpt"))
    dp.message.register(cmd_plan, Command("create_plan"))

# Обработчики команд меню
async def cmd_start(m: types.Message):
    # Сброс режима
    from bot import chat_mode
    chat_mode.clear()
    await m.answer(
        "👋 Привет! Выберите действие:",
        reply_markup=MAIN_KB
    )

async def cmd_generate(m: types.Message):
    from bot import chat_mode
    chat_mode[m.chat.id] = "generate"
    await m.answer(
        "🛠 Режим GENERATE: Пришлите фото, PDF или текст с задачами.\n"
        "Если файл/фото без подписи — после OCR введите подпись.",
        reply_markup=MAIN_KB
    )

async def cmd_check(m: types.Message):
    from bot import chat_mode
    chat_mode[m.chat.id] = "check"
    await m.answer(
        "📚 Режим CHECK: Пришлите фото, PDF или текст ДЗ — бот проверит его.",
        reply_markup=MAIN_KB
    )

async def cmd_talk(m: types.Message):
    from bot import chat_mode
    chat_mode[m.chat.id] = "talk"
    await m.answer(
        "💬 Режим TALK: Задавайте любой вопрос.",
        reply_markup=MAIN_KB
    )