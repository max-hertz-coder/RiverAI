from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app.keyboards import chat_menu as chat_kb

router = Router()

# State for ChatGPT conversation mode
class ChatGPTDialog(StatesGroup):
    active = State()

# Enter chat GPT mode
@router.callback_query(F.data.startswith("chat_gpt:"))
async def cb_chat_gpt(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    # Store student_id in state for reference
    await state.update_data(student_id=student_id)
    # Set state to chat active
    await state.set_state(ChatGPTDialog.active)
    await callback.message.edit_text("💬 Чат с GPT открыт. Напишите сообщение для ИИ (или /back для выхода):")

# Handle user messages in ChatGPT dialog state
@router.message(ChatGPTDialog.active)
async def handle_gpt_dialog_message(message: Message, state: FSMContext, bot: Bot):
    user_text = message.text
    if user_text.lower() in ("/exit", "/back"):
        # Exit chat mode
        await state.clear()
        data = await state.get_data()
        student_id = data.get("student_id")
        # Clear conversation context in worker's Redis via sending a reset command or simply dropping it on our side
        # We'll send a special task to worker to clear context if needed.
        task = {
            "type": "end_chat",
            "user_id": message.from_user.id,
            "student_id": student_id
        }
        from bot_app import rabbit_channel
        import json, aio_pika
        await rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode('utf-8')),
            routing_key="task_queue"
        )
        await message.answer("🔚 Чат с GPT завершён.", reply_markup=chat_kb.chat_menu_kb(student_id, lang="RU"))
    else:
        # Forward user message to worker for GPT processing
        data = await state.get_data()
        student_id = data.get("student_id")
        task = {
            "type": "chat_gpt",
            "user_id": message.from_user.id,
            "student_id": student_id,
            "message": user_text
        }
        from bot_app import rabbit_channel
        import json, aio_pika
        await rabbit_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(task).encode('utf-8')),
            routing_key="task_queue"
        )
        # Optionally, show typing action or acknowledgment
        await message.answer("💭 (сообщение отправлено ИИ, ожидайте ответ)...")
