import logging, json, aio_pika

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import config
from bot_app.keyboards.chat_menu import chat_menu_kb


router = Router()
logger = logging.getLogger(__name__)


router = Router()

class ChatState(StatesGroup):
    active = State()

@router.callback_query(F.data.startswith("chat:"))
async def cb_chat_start(query: CallbackQuery, state: FSMContext):
    sid = int(query.data.split(":",1)[1])
    await state.update_data(student_id=sid)
    await state.set_state(ChatState.active)
    await query.message.edit_text("💬 Напишите сообщение ИИ (или /back):")

@router.message(ChatState.active)
async def cb_chat_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    sid  = data["student_id"]
    txt  = message.text.strip()

    # если выходим
    ttype = "end_chat" if txt.lower() in ("/back","/exit") else "chat"
    task = {
        "type": ttype,
        "user_id": message.from_user.id,
        "student_id": sid,
        "message": txt
    }

    try:
        conn = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST,
            port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER,
            password=config.RABBITMQ_PASS,
        )
        ch = await conn.channel()
        await ch.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode("utf-8")),
            routing_key=config.TASK_QUEUE
        )
        await conn.close()
    except Exception:
        logging.exception("Ошибка публикации в очередь")
        return await message.answer("⚠️ Не удалось отправить, попробуйте позже")

    if ttype == "end_chat":
        await state.clear()
        await message.answer("🔚 Чат завершён", reply_markup=chat_menu_kb(sid))
    else:
        await message.answer("💭 Отправлено ИИ, ожидайте ответ…", reply_markup=chat_menu_kb(sid))
