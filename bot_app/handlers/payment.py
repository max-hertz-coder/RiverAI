# bot_app/handlers/payment.py
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot_app import config, database
from bot_app.database import db
from bot_app.database import payments_dao

router = Router()


def _provider_is_yookassa() -> bool:
    # ЕДИНЫЙ переключатель: config.PAYMENTS_PROVIDER = 'yookassa' | 'manual'
    return (getattr(config, "PAYMENTS_PROVIDER", "") or "").lower() == "yookassa"


def _admin_only(cb: CallbackQuery) -> bool:
    admin_id = int(getattr(config, "ADMIN_CHAT_ID", 0) or 0)
    return admin_id and (cb.from_user.id == admin_id)


def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])


def _kb_pay_and_check(pay_url: str, invoice_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment:{invoice_id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])


def _kb_manual(invoice_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"manual_paid:{invoice_id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="back:main")],
    ])


def _kb_admin_confirm(invoice_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить вручную", callback_data=f"confirm_payment:{invoice_id}")],
    ])


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(callback: CallbackQuery):
    """
    Формат callback_data: 'pay:<model>:<students>:<amount_rub>'
    """
    try:
        _, model, students_str, amount_str = callback.data.split(":")
        students = int(students_str)
        amount_rub = int(amount_str)
    except Exception:
        await callback.answer("Некорректные параметры оплаты", show_alert=True)
        return

    description = f"{model} x{students} / {callback.from_user.id}"
    metadata = {
        "user_id": callback.from_user.id,
        "model": model,
        "students": students,
    }

    # Попытка через YooKassa (если включена)
    if _provider_is_yookassa():
        try:
            from bot_app.payments.yookassa_client import create_invoice
            inv = create_invoice(amount_rub=amount_rub, description=description, metadata=metadata)

            await payments_dao.create_payment(
                user_id=callback.from_user.id,
                provider="yookassa",
                invoice_id=inv["payment_id"],
                amount_rub=amount_rub,
                label=description,
                meta=metadata,
                status=inv.get("status", "pending"),
            )

            await callback.message.edit_text(
                "💳 Счёт сформирован. Нажмите кнопку для оплаты:",
                reply_markup=_kb_pay_and_check(inv["pay_url"], inv["payment_id"])
            )
            await callback.answer()
            return
        except Exception as e:
            # Любая ошибка YooKassa → фолбэк на manual
            if config.ADMIN_CHAT_ID:
                try:
                    await callback.bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Ошибка YooKassa: {e}")
                except Exception:
                    pass
            # проваливаемся в manual ниже

    # Ручная оплата
    invoice_id = f"manual:{uuid.uuid4()}"
    await payments_dao.create_payment(
        user_id=callback.from_user.id,
        provider="manual",
        invoice_id=invoice_id,
        amount_rub=amount_rub,
        label=description,
        meta=metadata,
        status="manual_pending",
    )

    card = getattr(config, "MANUAL_PAYMENT_CARD", "") or "—"
    text = (
        "💳 <b>Ручная оплата</b>\n\n"
        f"Сумма: <b>{amount_rub}₽</b>\n"
        f"Карта: <code>{card}</code>\n\n"
        "После перевода нажмите «Я оплатил». Мы проверим платёж и активируем подписку."
    )
    await callback.message.edit_text(text, reply_markup=_kb_manual(invoice_id))
    await callback.answer()


@router.callback_query(F.data.startswith("manual_paid:"))
async def cb_manual_paid(callback: CallbackQuery):
    invoice_id = callback.data.split(":", 1)[1]
    await payments_dao.update_status(invoice_id, "manual_reported")

    # Уведомим админа
    admin_id = int(getattr(config, "ADMIN_CHAT_ID", 0) or 0)
    if admin_id:
        p = await payments_dao.get_payment(invoice_id)
        meta = (p or {}).get("meta") or {}
        model = meta.get("model", "standard")
        students = int(meta.get("students") or 0)

        try:
            await callback.bot.send_message(
                admin_id,
                f"🧾 Ручная оплата от @{callback.from_user.username or callback.from_user.id}\n"
                f"invoice_id: {invoice_id}\n"
                f"Модель: {model}, Ученики: {students}\n"
                f"Нажмите, чтобы подтвердить и активировать подписку.",
                reply_markup=_kb_admin_confirm(invoice_id),
            )
        except Exception:
            pass

    await callback.message.edit_text("✅ Заявка об оплате отправлена. Мы проверим перевод и активируем подписку.")
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def cb_check_payment(callback: CallbackQuery):
    invoice_id = callback.data.split(":", 1)[1]

    # В manual-режиме просто напомним пользователю
    if invoice_id.startswith("manual:") or not _provider_is_yookassa():
        await callback.answer("Заявка на ручную оплату в обработке. Ожидайте подтверждения.", show_alert=True)
        return

    # YooKassa-проверка
    try:
        from bot_app.payments.yookassa_client import fetch_status
        status = fetch_status(invoice_id)
    except Exception as e:
        if config.ADMIN_CHAT_ID:
            try:
                await callback.bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Ошибка проверки платежа: {e}")
            except Exception:
                pass
        await callback.answer("Ошибка проверки статуса. Попробуйте позже.", show_alert=True)
        return

    if status in ("succeeded", "waiting_for_capture"):
        await payments_dao.update_status(invoice_id, status)
        p = await payments_dao.get_payment(invoice_id)
        meta = (p or {}).get("meta") or {}
        model = meta.get("model", "standard")
        students = int(meta.get("students") or 0)
        until = datetime.now() + timedelta(days=30)

        await db.set_subscription(callback.from_user.id, model, students, until)
        await db.set_plan(callback.from_user.id, model)
        await database.db.reset_usage(callback.from_user.id)

        await callback.message.edit_text(f"✅ Оплата получена. Тариф '{model}' активирован до {until.date()}.")
        await callback.answer()
        return

    if status == "canceled":
        await payments_dao.update_status(invoice_id, "canceled")
        await callback.message.edit_text("❌ Оплата отменена.", reply_markup=_kb_back())
        await callback.answer()
        return

    await callback.answer("Платёж ещё не завершён. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data.startswith("confirm_payment:"))
async def cb_admin_confirm(callback: CallbackQuery):
    if not _admin_only(callback):
        return await callback.answer("Действие доступно только администратору", show_alert=True)

    invoice_id = callback.data.split(":", 1)[1]
    p = await payments_dao.get_payment(invoice_id)
    if not p:
        return await callback.answer("Платёж не найден", show_alert=True)

    await payments_dao.mark_paid(invoice_id)

    meta = (p or {}).get("meta") or {}
    user_id = int(meta.get("user_id") or 0)
    model = meta.get("model", "standard")
    students = int(meta.get("students") or 0)
    until = datetime.now() + timedelta(days=30)

    if user_id:
        await db.set_subscription(user_id, model, students, until)
        await db.set_plan(user_id, model)
        await database.db.reset_usage(user_id)
        try:
            await callback.bot.send_message(
                user_id, f"✅ Оплата подтверждена. Тариф '{model}' активирован до {until.date()}."
            )
        except Exception:
            pass

    await callback.message.edit_text(f"✅ Подтверждено вручную: {invoice_id}")
    await callback.answer("Готово")
