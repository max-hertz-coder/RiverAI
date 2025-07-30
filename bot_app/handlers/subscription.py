from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot_app.database import db
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
    callback = message  # подменим для совместимости
    await cb_subscription(callback, state)

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

    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить тариф", callback_data="change_plan")
    kb.button(text="Продлить подписку", callback_data="renew_plan")
    kb.button(text="История платежей", callback_data="payment_history")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)

    if isinstance(callback, Message):
        await callback.answer(sub_text, reply_markup=kb.as_markup())
    else:
        await callback.message.edit_text(sub_text, reply_markup=kb.as_markup())

# --- Изменить тариф
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

    total_generations = students * 8 * 4
    total_tokens = total_generations * 10000
    cost_per_million = 0.5 + 1.5
    multiplier = 1.0 if model == "standard" else 1.5
    price_usd = (total_tokens / 1_000_000) * cost_per_million * multiplier
    price_usd = round(price_usd, 2)
    price_rub = round(price_usd * 100, 2)

    admin_id = 922135759
    await callback.message.answer(
        f"\n\n💵 Тариф '{model}' для {students} учеников:\n"
        f"💰 Цена: ${price_usd} (~{price_rub}₽)\n\n"
        "Пожалуйста, произведите оплату. Как только вы оплатите, я напишу админу и активирую подписку."
    )

    await callback.bot.send_message(
        admin_id,
        f"\n\n💳 Новый платёж:\n"
        f"Пользователь: @{callback.from_user.username} ({callback.from_user.id})\n"
        f"Ученики: {students}\n"
        f"Модель: {model}\n"
        f"Сумма: ${price_usd} (~{price_rub}₽)\n"
        f"Нажмите, чтобы подтвердить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_sub:{callback.from_user.id}:{model}:{students}")]
        ])
    )

# --- Подтверждение админом
@router.callback_query(F.data.startswith("confirm_sub:"))
async def cb_admin_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id, model, students = int(parts[1]), parts[2], int(parts[3])
    until = datetime.now() + timedelta(days=30)
    await db.set_subscription(user_id, model, students, until)
    await callback.message.answer(f"✅ Подписка активирована пользователю {user_id} до {until.date()}")
    await callback.bot.send_message(user_id, f"✅ Подписка активирована до {until.date()}")

# --- Продление подписки
@router.callback_query(F.data == "renew_plan")
async def cb_renew_plan(callback: CallbackQuery):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    plan = user["plan"]
    students = user["students_limit"]
    until = datetime.now() + timedelta(days=30)
    await db.set_subscription(callback.from_user.id, plan, students, until)
    await callback.message.edit_text("Подписка продлена на 1 месяц ✅")

# --- История
@router.callback_query(F.data == "payment_history")
async def cb_payment_history(callback: CallbackQuery):
    await callback.message.edit_text(
        "История платежей пока недоступна.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="back:main")]
        ])
    )
