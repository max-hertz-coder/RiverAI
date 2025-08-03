from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot_app.database import db
from bot_app.keyboards.main_menu import bottom_menu_subscription_kb, bottom_menu_kb
from datetime import datetime, timedelta
import math

router = Router()

class PaymentFSM(StatesGroup):
    waiting_students = State()
    waiting_model = State()

def model_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Standard", callback_data="model:standard")],
        [InlineKeyboardButton(text="Premium", callback_data="model:premium")],
        [InlineKeyboardButton(text="Изменить количество учеников", callback_data="change_students")]
    ])

# --- Обработка текстовой кнопки 💳 Подписка
@router.message(F.text == "💳 Подписка")
async def msg_subscription(message: Message, state: FSMContext):
    user = await db.get_user_by_tg_id(message.from_user.id)
    if not user:
        return await message.answer("Пользователь не найден")

    plan = user.get("plan", "standard").capitalize()
    usage = user.get("usage_count", 0)
    limit = user.get("usage_limit", 0)
    sub_until = user.get("subscription_expires")

    if sub_until and isinstance(sub_until, str):
        sub_until = datetime.fromisoformat(sub_until)

    sub_text = f"📦 Тариф: {plan}\n🔢 Использовано: {usage}/{limit}"
    if sub_until and sub_until > datetime.now():
        sub_text += f"\n⏳ Активен до: {sub_until.date()}"
    else:
        sub_text += "\n⚠️ Подписка не активна"

    await message.answer(sub_text, reply_markup=bottom_menu_subscription_kb())

# --- Начало оформления подписки
@router.callback_query(F.data == "subscription")
async def cb_subscription(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user:
        return await callback.answer("Пользователь не найден", show_alert=True)

    plan = user.get("plan", "standard").capitalize()
    usage = user.get("usage_count", 0)
    limit = user.get("usage_limit", 0)
    sub_until = user.get("subscription_expires")

    if sub_until and isinstance(sub_until, str):
        sub_until = datetime.fromisoformat(sub_until)

    sub_text = f"📦 Тариф: {plan}\n🔢 Использовано: {usage}/{limit}"
    if sub_until and sub_until > datetime.now():
        sub_text += f"\n⏳ Активен до: {sub_until.date()}"
    else:
        sub_text += "\n⚠️ Подписка не активна"

    await callback.message.edit_text(sub_text, reply_markup=bottom_menu_subscription_kb())

# --- Изменить тариф
@router.message(F.text == "💳 Изменить тариф")
async def msg_change_plan(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(PaymentFSM.waiting_students)
    await message.answer("Сколько учеников вы планируете вести?")

@router.callback_query(F.data == "change_plan")
@router.callback_query(F.data == "change_students")
async def cb_change_plan(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PaymentFSM.waiting_students)
    await callback.message.edit_text("Сколько учеников вы планируете вести?")

@router.message(PaymentFSM.waiting_students)
async def process_students(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if count <= 0 or count > 1000:
            raise ValueError
    except ValueError:
        return await message.reply("Введите корректное число учеников.")
    await state.update_data(students=count)
    await state.set_state(PaymentFSM.waiting_model)
    await message.answer("Выберите модель:", reply_markup=model_choice_kb())

@router.callback_query(F.data.startswith("model:"))
async def process_model_choice(callback: CallbackQuery, state: FSMContext):
    model = callback.data.split(":")[1]
    data = await state.get_data()
    students = data["students"]
    await state.clear()

    # Автоматически оформляем подписку
    user_id = callback.from_user.id
    
    # Обновляем данные пользователя
    await db.update_user_plan(user_id, model, students)
    
    await callback.message.edit_text(
        f"✅ **Подписка оформлена!**\n\n"
        f"📦 Тариф: {model.capitalize()}\n"
        f"👥 Учеников: {students}\n"
        f"⏳ Срок: 30 дней\n\n"
        f"Теперь вы можете использовать все функции бота!",
        reply_markup=bottom_menu_subscription_kb()
    )

# --- Продлить подписку
@router.message(F.text == "💳 Продлить подписку")
async def msg_renew_plan(message: Message):
    await message.answer(
        "🔄 **Продление подписки**\n\n"
        "Для продления подписки напишите администратору @admin\n"
        "Укажите ваш текущий тариф и желаемый период продления.",
        reply_markup=bottom_menu_subscription_kb()
    )

@router.callback_query(F.data == "renew_plan")
async def cb_renew_plan(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔄 **Продление подписки**\n\n"
        "Для продления подписки напишите администратору @admin\n"
        "Укажите ваш текущий тариф и желаемый период продления.",
        reply_markup=bottom_menu_subscription_kb()
    )

# --- История платежей
@router.message(F.text == "📊 История платежей")
async def msg_payment_history(message: Message):
    await message.answer(
        "📊 **История платежей**\n\n"
        "Для получения истории платежей напишите администратору @admin",
        reply_markup=bottom_menu_subscription_kb()
    )

@router.callback_query(F.data == "payment_history")
async def cb_payment_history(callback: CallbackQuery):
    await callback.message.edit_text(
        "📊 **История платежей**\n\n"
        "Для получения истории платежей напишите администратору @admin",
        reply_markup=bottom_menu_subscription_kb()
    )

# --- Возврат в главное меню
@router.message(F.text == "← Главное меню")
async def back_to_main_from_subscription(message: Message):
    """Возврат в главное меню из подписки"""
    first_name = message.from_user.first_name or ""
    user = await db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?"
    )
    await message.answer(welcome, reply_markup=bottom_menu_kb(lang))

# --- Обработчики для совместимости с callback
@router.callback_query(F.data.startswith("confirm_sub:"))
async def cb_admin_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    plan = parts[2]
    students = int(parts[3])
    
    # Обновляем данные пользователя
    await db.update_user_plan(user_id, plan, students)
    
    await callback.answer("Подписка активирована!", show_alert=True)
    await callback.message.edit_text(
        f"✅ Подписка активирована!\n\n"
        f"📦 Тариф: {plan}\n"
        f"👥 Учеников: {students}\n"
        f"⏳ Срок: 30 дней",
        reply_markup=bottom_menu_subscription_kb()
    )

# --- Обработчики для английского языка ---
@router.message(F.text == "💳 Change Plan")
async def msg_change_plan_en(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(PaymentFSM.waiting_students)
    await message.answer("How many students do you plan to teach?")

@router.message(F.text == "💳 Renew Subscription")
async def msg_renew_plan_en(message: Message):
    await message.answer(
        "🔄 **Subscription Renewal**\n\n"
        "To renew your subscription, write to the administrator @admin\n"
        "Specify your current plan and desired renewal period.",
        reply_markup=bottom_menu_subscription_kb(lang="EN")
    )

@router.message(F.text == "📊 Payment History")
async def msg_payment_history_en(message: Message):
    await message.answer(
        "📊 **Payment History**\n\n"
        "To get payment history, write to the administrator @admin",
        reply_markup=bottom_menu_subscription_kb(lang="EN")
    )

@router.message(F.text == "← Back to Main")
async def back_to_main_from_subscription_en(message: Message):
    """Возврат в главное меню из подписки на английском"""
    first_name = message.from_user.first_name or ""
    user = await db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?"
    )
    await message.answer(welcome, reply_markup=bottom_menu_kb(lang))
