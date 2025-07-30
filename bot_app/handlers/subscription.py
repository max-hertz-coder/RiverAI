from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
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

    await callback.message.edit_text(sub_text, reply_markup=kb.as_markup())

# --- Изменить тариф
@router.callback_query(F.data == "change_plan")
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
    await message.answer("Выберите модель: `standard` или `premium`")


@router.message(PaymentFSM.waiting_model)
async def process_model(message: Message, state: FSMContext):
    model = message.text.strip().lower()
    if model not in ("standard", "premium"):
        return await message.reply("Допустимые значения: standard или premium")
    data = await state.get_data()
    students = data["students"]
    await state.clear()

    total_generations = students * 8 * 4  # 8 в неделю * 4 недели
    total_tokens = total_generations * 10000
    cost_per_million = 0.5 + 1.5  # input + output
    multiplier = 1.0 if model == "standard" else 1.5
    price_usd = (total_tokens / 1_000_000) * cost_per_million * multiplier
    price_usd = round(price_usd, 2)

    # TODO: интеграция с Юкассой
    admin_id = 922135759
    await message.answer(
        f"💵 Тариф '{model}' для {students} учеников:"
        f"💰 Цена: ${price_usd}"
        "Пожалуйста, произведите оплату. Как только вы оплатите, я напишу админу и активирую подписку."
    )
    await message.bot.send_message(
        admin_id,
        f"💳 Новый платёж:"
        f"Пользователь: @{message.from_user.username} ({message.from_user.id})"
        f"Ученики: {students}"
        f"Модель: {model}"
        f"Сумма: ${price_usd}"
        f"Нажмите, чтобы подтвердить:",
        reply_markup=InlineKeyboardBuilder()
        .button(text="✅ Подтвердить", callback_data=f"confirm_sub:{message.from_user.id}:{model}:{students}")
        .as_markup()
    )

# --- Админ подтверждает подписку
@router.callback_query(F.data.startswith("confirm_sub:"))
async def cb_admin_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id, model, students = int(parts[1]), parts[2], int(parts[3])
    until = datetime.now() + timedelta(days=30)
    await db.set_subscription(user_id, model, students, until)
    await callback.message.answer(f"✅ Подписка активирована пользователю {user_id} до {until.date()}")
    await callback.bot.send_message(user_id, f"✅ Подписка активирована до {until.date()}")


# --- Продление существующего тарифа
@router.callback_query(F.data == "renew_plan")
async def cb_renew_plan(callback: CallbackQuery):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    plan = user["plan"]
    students = user["students_limit"]
    until = datetime.now() + timedelta(days=30)
    await db.set_subscription(callback.from_user.id, plan, students, until)
    await callback.message.edit_text("Подписка продлена на 1 месяц ✅")

# --- История платежей
@router.callback_query(F.data == "payment_history")
async def cb_payment_history(callback: CallbackQuery):
    await callback.message.edit_text("История платежей пока недоступна.", reply_markup=InlineKeyboardBuilder().button(text="← Назад", callback_data="back:main").as_markup())