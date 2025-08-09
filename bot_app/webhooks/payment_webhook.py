# bot_app/webhooks/payment_webhook.py
"""
Простой aiohttp-вебхук для YooKassa:
- URL: /yookassa/webhook?token=<PAYMENT_WEBHOOK_TOKEN>
- Тело: JSON события (payment.succeeded / payment.canceled)
- Мы дополнительно подтверждаем статус через API и помечаем платеж в БД
- При успехе активируем подписку из metadata
Запуск:  uvicorn bot_app.webhooks.payment_webhook:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot

from bot_app import config, database
from bot_app.database import db
from bot_app.database import payments_dao
from bot_app.payments.yookassa_client import fetch_status

app = FastAPI()
bot = Bot(token=config.BOT_TOKEN)


@app.post("/yookassa/webhook")
async def yookassa_webhook(req: Request):
    token = req.query_params.get("token", "")
    if not config.PAYMENT_WEBHOOK_TOKEN or token != config.PAYMENT_WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    data: Dict[str, Any] = await req.json()
    obj = (data or {}).get("object") or {}
    payment_id = obj.get("id")
    if not payment_id:
        raise HTTPException(400, "payment id missing")

    status = fetch_status(payment_id)
    await payments_dao.update_status(payment_id, status)

    if status in ("succeeded", "waiting_for_capture"):
        p = await payments_dao.get_payment(payment_id)
        meta = (p or {}).get("meta") or {}
        user_id = int(meta.get("user_id") or 0)
        model = meta.get("model", "standard")
        students = int(meta.get("students") or 0)

        until = datetime.now() + timedelta(days=30)
        await db.set_subscription(user_id, model, students, until)
        await db.set_plan(user_id, model)
        await database.db.reset_usage(user_id)

        # уведомим пользователя
        if user_id:
            await bot.send_message(user_id, f"✅ Оплата получена. Тариф '{model}' активирован до {until.date()}.")

    return {"ok": True}
