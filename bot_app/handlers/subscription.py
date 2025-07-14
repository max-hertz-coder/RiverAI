from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot_app import database
from bot_app.keyboards.main_menu import back_button

router = Router()

@router.callback_query(F.data == "subscription")
async def cb_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await database.db.get_user_by_tg_id(user_id)
    if not user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return
    plan = user["plan"].capitalize() if user["plan"] else "Basic"
    usage = user["usage_count"]
    limit = user["usage_limit"]
    text = f"📦 Ваш тариф: {plan}\n"
    text += f"Доступно запросов: {usage}/{limit} в месяц"
    await callback.message.edit_text(text, reply_markup=
                                     # Inline buttons for upgrade and history
                                     # We'll provide two simple buttons and back
                                     back_button("← Назад", "back:main"))

    # We add inline buttons: "Upgrade to Premium", "Payment history"
    # For brevity, let's edit keyboard to include them
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="Перейти на Премиум", callback_data="upgrade_plan")
    kb.button(text="История платежей", callback_data="payment_history")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data == "upgrade_plan")
async def cb_upgrade_plan(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await database.db.get_user_by_tg_id(user_id)
    if user and user["plan"] == "premium":
        await callback.answer("У вас уже Премиум-тариф.", show_alert=True)
    else:
        # Upgrade to premium
        await database.db.set_plan(user_id, "premium", new_limit=1000)  # Premium limit example
        await callback.answer("Тариф обновлен до Премиум!", show_alert=True)
        # Refresh subscription info
        user = await database.db.get_user_by_tg_id(user_id)
        plan = user["plan"].capitalize()
        usage = user["usage_count"]
        limit = user["usage_limit"]
        text = f"📦 Ваш тариф: {plan}\nДоступно запросов: {usage}/{limit} в месяц"
        # Keep the same keyboard
        await callback.message.edit_text(text, reply_markup=callback.message.reply_markup)

@router.callback_query(F.data == "payment_history")
async def cb_payment_history(callback: CallbackQuery):
    # In a real implementation, fetch payments from DB. Here, just a placeholder.
    text = "История платежей:\n(пока нет данных)"
    await callback.message.edit_text(text, reply_markup=back_button("← Назад", "back:main"))
