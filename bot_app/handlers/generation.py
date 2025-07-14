from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app.keyboards import chat_menu as chat_kb
from bot_app import database
from bot_app import config

router = Router()

# States for prompting generation descriptions and refinements
class GeneratePlanFSM(StatesGroup):
    waiting_for_description = State()

class GenerateTasksFSM(StatesGroup):
    waiting_for_description = State()

class HomeworkCheckFSM(StatesGroup):
    waiting_for_file = State()

class RefineFSM(StatesGroup):
    waiting_for_plan_feedback = State()
    waiting_for_tasks_feedback = State()
    waiting_for_check_feedback = State()

# Handle "Generate Study Plan" button
@router.callback_query(F.data.startswith("gen_plan:"))
async def cb_generate_plan(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    # Ask user for description of what to generate
    await state.update_data(student_id=student_id)
    await state.set_state(GeneratePlanFSM.waiting_for_description)
    await callback.message.edit_text("Опишите, что нужно сгенерировать (тема, формат, длительность):", 
                                     reply_markup=chat_kb.back_button("← Отмена", "back:chat"))

# Receive plan description and send task to worker
@router.message(GeneratePlanFSM.waiting_for_description)
async def process_plan_description(message: Message, state: FSMContext):
    description = message.text.strip()
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    # Send task to RabbitMQ (to worker)
    # Prepare task payload
    task = {
        "type": "generate_plan",
        "user_id": user_id,
        "student_id": student_id,
        "description": description
    }
    # Use aio_pika channel stored in config (set up in main)
    from bot_app import rabbit_channel  # use global channel from main
    import json
    await rabbit_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(task).encode('utf-8')),
        routing_key=config.RABBITMQ_TASK_QUEUE
    )
    await message.answer("🕔 Генерируется учебный план, пожалуйста подождите...")
    # Clear state (result will be handled by result consumer)
    await state.clear()

# Handle "Generate Tasks" button
@router.callback_query(F.data.startswith("gen_tasks:"))
async def cb_generate_tasks(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    await state.update_data(student_id=student_id)
    await state.set_state(GenerateTasksFSM.waiting_for_description)
    await callback.message.edit_text("Введите запрос для генерации заданий:", 
                                     reply_markup=chat_kb.back_button("← Отмена", "back:chat"))

@router.message(GenerateTasksFSM.waiting_for_description)
async def process_tasks_description(message: Message, state: FSMContext):
    description = message.text.strip()
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    task = {
        "type": "generate_tasks",
        "user_id": user_id,
        "student_id": student_id,
        "description": description
    }
    from bot_app import rabbit_channel
    import json, aio_pika
    await rabbit_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(task).encode('utf-8')),
        routing_key=config.RABBITMQ_TASK_QUEUE
    )
    await message.answer("🕔 Генерируются задания, пожалуйста подождите...")
    await state.clear()

# Handle "Check Homework" button
@router.callback_query(F.data.startswith("check_hw:"))
async def cb_check_homework(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    await state.update_data(student_id=student_id)
    await state.set_state(HomeworkCheckFSM.waiting_for_file)
    await callback.message.edit_text("Загрузите файл с решением для проверки:", 
                                     reply_markup=chat_kb.back_button("← Отмена", "back:chat"))

@router.message(HomeworkCheckFSM.waiting_for_file, F.document)
async def process_homework_file(message: Message, state: FSMContext):
    # User sent a document for homework
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    # Download the file from Telegram
    file = await message.document.download(destination=None)
    file_bytes = await message.document.read()  # file content in memory
    # Try to extract text if possible (assuming a text-based file)
    solution_text = None
    try:
        solution_text = file_bytes.decode('utf-8')
    except Exception:
        solution_text = None
    # Prepare task payload
    task = {
        "type": "check_homework",
        "user_id": user_id,
        "student_id": student_id,
        "filename": message.document.file_name or "",
        "solution_text": solution_text
    }
    from bot_app import rabbit_channel
    import json, aio_pika
    await rabbit_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(task).encode('utf-8')),
        routing_key=config.RABBITMQ_TASK_QUEUE
    )
    await message.reply("🕔 Выполняется проверка домашнего задания, пожалуйста подождите...")
    await state.clear()

# Refinement flows for "Correct/Refine" buttons after results
@router.callback_query(F.data.startswith("refine_plan:"))
async def cb_refine_plan(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    await state.update_data(student_id=student_id)
    await state.set_state(RefineFSM.waiting_for_plan_feedback)
    await callback.message.reply("Введите уточнения или пожелания для корректировки плана:")

@router.message(RefineFSM.waiting_for_plan_feedback)
async def process_plan_refinement(message: Message, state: FSMContext):
    feedback = message.text.strip()
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    # Treat refinement as a new generate_plan request (possibly could combine with previous description)
    task = {
        "type": "generate_plan",
        "user_id": user_id,
        "student_id": student_id,
        "description": feedback
    }
    from bot_app import rabbit_channel
    import json, aio_pika
    await rabbit_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(task).encode('utf-8')),
        routing_key=config.RABBITMQ_TASK_QUEUE
    )
    await message.answer("🔄 Повторная генерация плана, подождите...")
    await state.clear()

@router.callback_query(F.data.startswith("refine_tasks:"))
async def cb_refine_tasks(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    await state.update_data(student_id=student_id)
    await state.set_state(RefineFSM.waiting_for_tasks_feedback)
    await callback.message.reply("Введите уточнения для корректировки заданий:")

@router.message(RefineFSM.waiting_for_tasks_feedback)
async def process_tasks_refinement(message: Message, state: FSMContext):
    feedback = message.text.strip()
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    task = {
        "type": "generate_tasks",
        "user_id": user_id,
        "student_id": student_id,
        "description": feedback
    }
    from bot_app import rabbit_channel
    import json, aio_pika
    await rabbit_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(task).encode('utf-8')),
        routing_key=config.RABBITMQ_TASK_QUEUE
    )
    await message.answer("🔄 Повторная генерация заданий, подождите...")
    await state.clear()

@router.callback_query(F.data.startswith("refine_check:"))
async def cb_refine_check(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    await state.update_data(student_id=student_id)
    await state.set_state(RefineFSM.waiting_for_check_feedback)
    await callback.message.reply("Введите замечания или дополнительные указания для повторной проверки:")

@router.message(RefineFSM.waiting_for_check_feedback)
async def process_check_refinement(message: Message, state: FSMContext):
    feedback = message.text.strip()
    data = await state.get_data()
    student_id = data.get("student_id")
    user_id = message.from_user.id
    task = {
        "type": "check_homework",
        "user_id": user_id,
        "student_id": student_id,
        "filename": "",  # no new file, just text feedback
        "solution_text": feedback
    }
    from bot_app import rabbit_channel
    import json, aio_pika
    await rabbit_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(task).encode('utf-8')),
        routing_key=config.RABBITMQ_TASK_QUEUE
    )
    await message.answer("🔄 Повторная проверка выполняется, подождите...")
    await state.clear()
