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


# ======== Pricing & proration helpers (локально, чтобы не плодить зависимости) ========

def _compute_month_price_rub(model: str, students: int) -> int:
    """
    Твоя текущая модель цены (как была в subscription.py):
    price ~= (students * 8 * 4 * 10000 tokens) * 2 руб/1M * (multiplier)
    затем округление до сотен.
    """
    total_generations = students * 8 * 4
    total_tokens = total_generations * 10_000
    cost_per_million = 2.0
    multiplier = 1.0 if model == "standard" else 1.5
    price_rub = int(round((total_tokens / 1_000_000) * cost_per_million * 100 * multiplier))
    price_rub = ((price_rub + 50) // 100) * 100
    return max(price_rub, 0)


def _prorate(user_dict: dict, new_model: str, new_students: int) -> dict:
    """
    Возвращает dict с разложением proration:
    {
      'old_plan', 'old_students', 'sub_until', 'days_left',
      'old_price', 'new_price', 'credit', 'final_amount'
    }
    Кредит считаем только если активная платная подписка (не trial) и дата в будущем.
    """
    now = datetime.now()
    old_plan = (user_dict.get("plan") or "standard").lower()
    old_students = int(user_dict.get("students_limit") or 0)
    sub_until = user_dict.get("subscription_expires")

    # нормализуем дату
    if sub_until and isinstance(sub_until, str):
        try:
            sub_until = datetime.fromisoformat(sub_until)
        except Exception:
            sub_until = None

    is_paid_active = (old_plan != "trial") and (sub_until and sub_until > now)

    old_price = _compute_month_price_rub(old_plan, old_students) if is_paid_active else 0
    new_price = _compute_month_price_rub(new_model, new_students)

    days_left = 0
    if is_paid_active:
        try:
            days_left = max((sub_until.date() - now.date()).days, 0)
        except Exception:
            days_left = 0

    credit = int(round((old_price / 30.0) * days_left)) if days_left > 0 else 0
    final_amount = max(new_price - credit, 0)

    return {
        "old_plan": old_plan,
        "old_students": old_students,
        "sub_until": sub_until,
        "days_left": days_left,
        "old_price": int(old_price),
        "new_price": int(new_price),
        "credit": int(credit),
        "final_amount": int(final_amount),
    }


# ======== Handlers ========

@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(callback: CallbackQuery):
    """
    Формат callback_data: 'pay:<model>:<students>:<amount_rub>'
    amount_rub — может быть 0, если proration покрыла стоимость (тогда переключаем тариф бесплатно).
    """
    try:
        _, model, students_str, _amount_str = callback.data.split(":")
        students = int(students_str)
    except Exception:
        await callback.answer("Некорректные параметры оплаты", show_alert=True)
        return

    # Пересчёт по факту вызова (из актуального состояния пользователя)
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    pr = _prorate(user, model, students)
    amount_rub = pr["final_amount"]

    # Если к оплате 0 — переключаем тариф без счёта, срок оставляем прежним
    if amount_rub <= 0:
        until = pr["sub_until"]
        if not until or until <= datetime.now():
            # теоретически сюда попадём редко (кредит 0 и подписки нет) — тогда даём 30 дней
            until = datetime.now() + timedelta(days=30)

        await db.set_subscription(callback.from_user.id, model, students, until)
        await db.set_plan(callback.from_user.id, model)
        await database.db.reset_usage(callback.from_user.id)

        await callback.message.edit_text(
            f"✅ Тариф переключён бесплатно. Новый тариф '{model}' действует до {until.date()}."
        )
        return await callback.answer()

    description = f"{model} x{students} / {callback.from_user.id}"
    metadata = {
        "user_id": callback.from_user.id,
        "model": model,
        "students": students,
        # подробности proration для прозрачности
        "old_plan": pr["old_plan"],
        "old_students": pr["old_students"],
        "days_left": pr["days_left"],
        "old_price": pr["old_price"],
        "new_price": pr["new_price"],
        "credit": pr["credit"],
        "final_amount": pr["final_amount"],
    }

    # Попытка YooKassa (если включена)
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
            if config.ADMIN_CHAT_ID:
                try:
                    await callback.bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Ошибка YooKassa: {e}")
                except Exception:
                    pass
            # идём в manual ниже

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
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_kb_manual(invoice_id))
    await callback.answer()


@router.callback_query(F.data.startswith("manual_paid:"))
async def cb_manual_paid(callback: CallbackQuery):
    invoice_id = callback.data.split(":", 1)[1]
    await payments_dao.update_status(invoice_id, "manual_reported")

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

    await callback.message.edit_text("✅ Заявка об оплате отправлена. Мы проверим платёж и активируем подписку.")
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def cb_check_payment(callback: CallbackQuery):
    invoice_id = callback.data.split(":", 1)[1]

    if invoice_id.startswith("manual:") or not _provider_is_yookassa():
        await callback.answer("Заявка на ручную оплату в обработке. Ожидайте подтверждения.", show_alert=True)
        return

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
