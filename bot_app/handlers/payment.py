# bot_app/handlers/payment.py
from __future__ import annotations
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot_app import config, database
from bot_app.database import db
from bot_app.database import payments_dao
from bot_app.payments.yookassa_client import create_invoice, fetch_status

router = Router()


def _confirm_kb(payment_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment:{payment_id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(callback: CallbackQuery):
    # формат: pay:<model>:<students>:<amount_rub>
    _, model, students_str, amount_str = callback.data.split(":")
    students = int(students_str)
    amount_rub = int(amount_str)

    description = f"{model} x{students} / {callback.from_user.id}"
    metadata = {
        "user_id": callback.from_user.id,
        "model": model,
        "students": students,
    }

    try:
        invoice = create_invoice(amount_rub=amount_rub, description=description, metadata=metadata)
    except Exception as e:
        await callback.answer("Не удалось создать счёт", show_alert=True)
        # Сообщим админу
        await callback.bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Ошибка создания счёта: {e}")
        return

    await payments_dao.create_payment(
        user_id=callback.from_user.id,
        provider="yookassa",
        invoice_id=invoice["payment_id"],
        amount_rub=amount_rub,
        label=description,
        meta=metadata,
        status=invoice.get("status", "pending"),
    )

    await callback.message.edit_text(
        "💳 Счёт сформирован. Нажмите кнопку для оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=invoice["pay_url"])],
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment:{invoice['payment_id']}")],
            [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def cb_check_payment(callback: CallbackQuery):
    payment_id = callback.data.split(":", 1)[1]
    try:
        status = fetch_status(payment_id)
    except Exception as e:
        await callback.answer("Ошибка проверки статуса", show_alert=True)
        await callback.bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Ошибка fetch_status: {e}")
        return

    if status in ("succeeded", "waiting_for_capture"):
        await payments_dao.update_status(payment_id, status)
        # Читаем метаданные из DAO
        p = await payments_dao.get_payment(payment_id)
        meta = (p or {}).get("meta") or {}
        model = meta.get("model", "standard")
        students = int(meta.get("students") or 0)
        until = datetime.now() + timedelta(days=30)

        await db.set_subscription(callback.from_user.id, model, students, until)
        await db.set_plan(callback.from_user.id, model)
        await database.db.reset_usage(callback.from_user.id)

        await callback.message.edit_text(
            f"✅ Оплата получена. Тариф '{model}' активирован до {until.date()}."
        )
        await callback.answer()
    elif status == "canceled":
        await payments_dao.update_status(payment_id, "canceled")
        await callback.message.edit_text("❌ Оплата отменена.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data="back:main")]]
        ))
        await callback.answer()
    else:
        await callback.answer("Платёж ещё не завершён. Попробуйте позже.", show_alert=True)
