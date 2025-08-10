from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot_app import config
from bot_app.database import db
from bot_app.database import payments_dao

router = Router()

class PaymentFSM(StatesGroup):
    waiting_students = State()
    waiting_model = State()

def model_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Standard", callback_data="model:standard")],
        [InlineKeyboardButton(text="Premium", callback_data="model:premium")],
        [InlineKeyboardButton(text="Изменить количество учеников", callback_data="change_students")],
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])

@router.message(F.text == "💳 Подписка")
async def msg_subscription(message: Message, state: FSMContext):
    await cb_subscription(message, state)

@router.callback_query(F.data == "subscription")
async def cb_subscription(callback: CallbackQuery | Message, state: FSMContext):
    user_id = callback.from_user.id if isinstance(callback, CallbackQuery) else callback.from_user.id
    user = await db.get_user_by_tg_id(user_id)
    if not user:
        if isinstance(callback, CallbackQuery):
            return await callback.answer("Пользователь не найден", show_alert=True)
        return await callback.answer("Пользователь не найден")

    plan = (user.get("plan") or "standard").capitalize()
    usage = int(user.get("usage_count") or 0)
    limit = int(user.get("usage_limit") or 0)
    sub_until = user.get("subscription_expires")
    if sub_until and isinstance(sub_until, str):
        try:
            sub_until = datetime.fromisoformat(sub_until)
        except Exception:
            sub_until = None
    sub_text = f"📦 Тариф: {plan}\n🔢 Использовано: {usage}/{limit}"
    sub_text += f"\n⏳ Активен до: {sub_until.date()}" if (sub_until and sub_until > datetime.now()) else "\n⚠️ Подписка не активна"

    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить тариф", callback_data="change_plan")
    kb.button(text="История платежей", callback_data="payment_history")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)

    if isinstance(callback, Message):
        await callback.answer(sub_text, reply_markup=kb.as_markup())
    else:
        await callback.message.edit_text(sub_text, reply_markup=kb.as_markup())
        await callback.answer()

@router.callback_query(F.data == "change_plan")
@router.callback_query(F.data == "change_students")
async def cb_change_plan(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PaymentFSM.waiting_students)
    await callback.message.edit_text("Сколько учеников вы планируете вести?")
    await callback.answer()

@router.message(PaymentFSM.waiting_students)
async def process_students(message: Message, state: FSMContext):
    try:
        count = int((message.text or "").strip())
        if count <= 0 or count > 1000:
            raise ValueError
    except ValueError:
        return await message.reply("Введите корректное число учеников (1–1000).")
    await state.update_data(students=count)
    await state.set_state(PaymentFSM.waiting_model)
    await message.answer("Выберите модель:", reply_markup=model_choice_kb())

@router.callback_query(F.data.startswith("model:"))
async def process_model_choice(callback: CallbackQuery, state: FSMContext):
    model = callback.data.split(":", 1)[1]
    data = await state.get_data()
    students = int(data["students"])
    await state.clear()

    # Прикидка цены
    total_generations = students * 8 * 4
    total_tokens = total_generations * 10_000
    cost_per_million = 2.0
    multiplier = 1.0 if model == "standard" else 1.5
    price_rub = int(round((total_tokens / 1_000_000) * cost_per_million * 100 * multiplier))
    price_rub = ((price_rub + 50) // 100) * 100

    pay_cb = f"pay:{model}:{students}:{price_rub}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {price_rub}₽", callback_data=pay_cb)],
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])
    # текст без упоминания конкретного провайдера
    await callback.message.answer(
        f"💵 Тариф '{model}' для {students} учеников.\n💰 Цена: {price_rub}₽\n\nНажмите «Оплатить», чтобы продолжить.",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data == "payment_history")
async def cb_payment_history(callback: CallbackQuery):
    rows = await payments_dao.get_user_payments(callback.from_user.id, limit=20)
    if not rows:
        await callback.message.edit_text(
            "История платежей пуста.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back:main")]
            ])
        )
        return await callback.answer()

    lines = []
    for r in rows:
        status = r["status"]
        amt = r["amount_rub"]
        dt = r["created_at"].strftime("%Y-%m-%d")
        lines.append(f"• {dt} — {amt}₽ — {status}")

    await callback.message.edit_text(
        "Последние платежи:\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="back:main")]
        ])
    )
    await callback.answer()
