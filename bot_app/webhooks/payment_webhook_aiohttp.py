# bot_app/webhooks/payment_webhook_aiohttp.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, Any

from aiohttp import web
from aiogram import Bot

from bot_app import config, database
from bot_app.database import db
from bot_app.database import payments_dao
from bot_app.payments.yookassa_client import fetch_status

async def yookassa_webhook(request: web.Request) -> web.Response:
    token = request.query.get("token", "")
    if not config.PAYMENT_WEBHOOK_TOKEN or token != config.PAYMENT_WEBHOOK_TOKEN:
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad json"}, status=400)

    obj = (payload or {}).get("object") or {}
    payment_id = obj.get("id")
    if not payment_id:
        return web.json_response({"ok": False, "error": "id missing"}, status=400)

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

        if user_id:
            bot = Bot(token=config.BOT_TOKEN)
            await bot.send_message(user_id, f"✅ Оплата получена. Тариф '{model}' активирован до {until.date()}.")
            await bot.session.close()

    return web.json_response({"ok": True})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/yookassa/webhook", yookassa_webhook)
    return app
