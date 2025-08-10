# bot_app/run_payment_web.py
from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timedelta

from aiohttp import web
from aiogram import Bot

from bot_app import config, database
from bot_app.database.db import init_db_pool
from bot_app.database import payments_dao, db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("payments-web")

PAYMENT_WEBHOOK_TOKEN = (
    getattr(config, "PAYMENT_WEBHOOK_TOKEN", "") or os.environ.get("PAYMENT_WEBHOOK_TOKEN", "")
)
POSTGRES_DSN = (
    getattr(config, "WORKER_POSTGRES_DSN", "") or os.environ.get("WORKER_POSTGRES_DSN", "")
)
WEB_PORT = int(os.environ.get("PAYMENT_WEBHOOK_PORT") or getattr(config, "PAYMENT_WEBHOOK_PORT", 8080) or 8080)
BOT_TOKEN = getattr(config, "BOT_TOKEN", "") or os.environ.get("BOT_TOKEN", "")


async def _activate_subscription_if_needed(payment_id: str, new_status: str) -> None:
    """
    Идемпотентная активация: делаем только если ещё не 'succeeded'.
    """
    p = await payments_dao.get_payment(payment_id)
    if not p:
        return
    if (p.get("status") or "").lower() == "succeeded":
        return  # уже активирован ранее

    meta = (p.get("meta") or {})
    user_id = int(meta.get("user_id") or 0)
    model = meta.get("model", "standard")
    students = int(meta.get("students") or 0)

    if new_status in ("succeeded", "waiting_for_capture") and user_id:
        until = datetime.now() + timedelta(days=30)
        await db.set_subscription(user_id, model, students, until)  # :contentReference[oaicite:3]{index=3}
        await db.set_plan(user_id, model)                           # :contentReference[oaicite:4]{index=4}
        await database.db.reset_usage(user_id)                      # :contentReference[oaicite:5]{index=5}

        # Сообщим пользователю, если есть токен бота
        if BOT_TOKEN:
            try:
                bot = Bot(BOT_TOKEN)
                await bot.send_message(user_id, f"✅ Оплата получена. Тариф '{model}' активирован до {until.date()}.")
                await bot.session.close()
            except Exception:
                log.exception("Не удалось отправить уведомление пользователю %s", user_id)


async def yookassa_webhook(request: web.Request) -> web.StreamResponse:
    # 1) Проверка токена в query (?token=)
    token = request.query.get("token")
    if not token or token != PAYMENT_WEBHOOK_TOKEN:
        return web.Response(status=403, text="Forbidden")

    # 2) Парсим JSON от YooKassa
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    obj = payload.get("object") or {}
    payment_id = obj.get("id") or ""
    status = (obj.get("status") or "").lower()

    # Сумма/описание могут пригодиться при первом апсерте
    amount_value = 0
    try:
        amount_value = int(float(((obj.get("amount") or {}).get("value") or "0")))
    except Exception:
        pass
    description = payload.get("description") or ""
    metadata = obj.get("metadata") or {}

    if not payment_id:
        return web.Response(status=400, text="Missing payment_id")

    # 3) Апсерт платежа
    existing = await payments_dao.get_payment(payment_id)  # :contentReference[oaicite:6]{index=6}
    if not existing:
        try:
            await payments_dao.create_payment(
                user_id=int(metadata.get("user_id") or 0),
                provider="yookassa",
                invoice_id=payment_id,
                amount_rub=amount_value,
                label=description,
                meta=metadata,
                status=status or "pending",
            )  # :contentReference[oaicite:7]{index=7}
        except Exception:
            log.exception("Не удалось создать запись payment %s", payment_id)

    # 4) Обновим статус
    if status:
        try:
            await payments_dao.update_status(payment_id, status)  # :contentReference[oaicite:8]{index=8}
        except Exception:
            log.exception("Не удалось обновить статус payment %s -> %s", payment_id, status)

    # 5) При нужном статусе — активируем подписку (идемпотентно)
    await _activate_subscription_if_needed(payment_id, status)  # логика как в твоём хендлере :contentReference[oaicite:9]{index=9}

    return web.json_response({"ok": True})

async def health(request: web.Request) -> web.StreamResponse:
    return web.Response(text="ok")

async def pay_ping(request: web.Request) -> web.StreamResponse:
    return web.json_response({"ok": True, "msg": "pay endpoint is alive"})

async def on_startup(app: web.Application):
    if not POSTGRES_DSN:
        raise RuntimeError("WORKER_POSTGRES_DSN is not set")
    await init_db_pool(POSTGRES_DSN)
    log.info("DB pool initialized")

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/pay/ping", pay_ping)  # просто чтобы /pay/ тоже был проброшен
    app.router.add_post("/yookassa/webhook", yookassa_webhook)
    app.on_startup.append(on_startup)
    return app

if __name__ == "__main__":
    web.run_app(build_app(), port=WEB_PORT)
