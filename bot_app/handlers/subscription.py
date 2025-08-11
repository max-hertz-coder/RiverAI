from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

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

def _compute_month_price_rub(model: str, students: int) -> int:
    total_generations = students * 8 * 4
    total_tokens = total_generations * 10_000
    cost_per_million = 2.0
    multiplier = 1.0 if model == "standard" else 1.5
    price_rub = int(round((total_tokens / 1_000_000) * cost_per_million * 100 * multiplier))
    price_rub = ((price_rub + 50) // 100) * 100
    return max(price_rub, 0)

def _make_proration_text(user: dict, new_model: str, new_students: int) -> tuple[int, str]:
    """
    Возвращает (final_amount, text_for_user)
    Смотрим активна ли платная подписка (не trial) и есть ли дни до окончания.
    """
    now = datetime.now()
    plan = (user.get("plan") or "standard").lower()
    old_students = int(user.get("students_limit") or 0)
    sub_until = user.get("subscription_expires")
    if sub_until and isinstance(sub_until, str):
        try:
            sub_until = datetime.fromisoformat(sub_until)
        except Exception:
            sub_until = None

    is_paid_active = (plan != "trial") and (sub_until and sub_until > now)

    new_price = _compute_month_price_rub(new_model, new_students)
    if not is_paid_active:
        text = (
            f"💵 Тариф '{new_model}' для {new_students} учеников.\n"
            f"💰 Цена: {new_price}₽\n\nНажмите «Оплатить», чтобы продолжить."
        )
        return new_price, text

    old_price = _compute_month_price_rub(plan, old_students)
    try:
        days_left = max((sub_until.date() - now.date()).days, 0)
    except Exception:
        days_left = 0

    credit = int(round((old_price / 30.0) * days_left)) if days_left > 0 else 0
    final_amount = max(new_price - credit, 0)

    text = (
        f"🔄 Смена тарифа\n"
        f"• Текущий: {plan} ×{old_students}\n"
        f"• Действует до: {sub_until.date() if sub_until else '—'}\n"
        f"• Осталось дней: {days_left} → кредит {credit}₽\n\n"
        f"• Новый: {new_model} ×{new_students} = {new_price}₽\n"
        f"➡️ К оплате: <b>{final_amount}₽</b>"
        + ("\n\nСумма 0₽ — переключим тариф бесплатно, срок окончания останется прежним." if final_amount == 0 else "")
    )
    return final_amount, text

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

    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user:
        return await callback.answer("Пользователь не найден", show_alert=True)

    final_amount, text = _make_proration_text(user, model, students)

    pay_cb = f"pay:{model}:{students}:{final_amount}"
    btn_text = "Переключить бесплатно" if final_amount == 0 else f"Оплатить {final_amount}₽"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=pay_cb)],
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])

    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
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
