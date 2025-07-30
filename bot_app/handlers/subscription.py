from aiogram import Router, F
from aiogram.types import CallbackQuery
from bot_app.database import db
from bot_app.keyboards.main_menu import back_button
from aiogram.types import Message
from aiogram import F

router = Router()

@router.callback_query(F.data == "subscription")
async def cb_subscription(callback: CallbackQuery):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user:
        return await callback.answer("Пользователь не найден", show_alert=True)
    plan = (user["plan"] or "basic").capitalize()
    usage, limit = user["usage_count"], user["usage_limit"]
    text = f"📦 Тариф: {plan}\n🔢 Использовано: {usage}/{limit}"
    # Построим кнопки
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="Перейти на Премиум", callback_data="upgrade_plan")
    kb.button(text="История платежей", callback_data="payment_history")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data == "upgrade_plan")
async def cb_upgrade(callback: CallbackQuery):
    uid = callback.from_user.id
    user = await db.get_user_by_tg_id(uid)
    if user["plan"] == "premium":
        return await callback.answer("У вас уже премиум", show_alert=True)
    await db.set_plan(uid, "premium", new_limit=1000)
    await callback.answer("Тариф обновлён до Премиум!", show_alert=True)
    await cb_subscription(callback)

@router.callback_query(F.data == "payment_history")
async def cb_history(callback: CallbackQuery):
    text = "История платежей:\n(пока нет данных)"
    await callback.message.edit_text(text, reply_markup=back_button("← Назад","back:main"))




@router.message(F.text == "💳 Подписка")
async def msg_subscription(message: Message):
    await cb_subscription(message)