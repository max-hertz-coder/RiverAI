# bot_app/webhooks/payment_webhook_aiohttp.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from aiohttp import web
from aiogram import Bot

from bot_app import config, database
from bot_app.database import db
from bot_app.database import payments_dao
from bot_app.payments.yookassa_client import fetch_status

HTML_BASE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; padding:40px; background:#0f172a; color:#e5e7eb; }}
  .card {{ max-width:680px; margin:0 auto; background:#111827; border-radius:16px; padding:28px; box-shadow:0 6px 24px rgba(0,0,0,.35); }}
  h1 {{ margin:0 0 12px; font-size:24px; }}
  p {{ margin:8px 0; line-height:1.5; color:#cbd5e1; }}
  .ok {{ color:#22c55e }}
  .warn {{ color:#f59e0b }}
  .err {{ color:#ef4444 }}
  a.btn {{ display:inline-block; padding:10px 14px; border-radius:10px; background:#2563eb; color:#fff; text-decoration:none; margin-top:16px; }}
  code {{ background:#0b1220; padding:2px 6px; border-radius:6px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{h1}</h1>
    {content}
  </div>
</body>
</html>
"""

def _html(title: str, h1: str, content: str) -> web.Response:
    return web.Response(text=HTML_BASE.format(title=title, h1=h1, content=content), content_type="text/html; charset=utf-8")


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
            try:
                await bot.send_message(user_id, f"✅ Оплата получена. Тариф '{model}' активирован до {until.date()}.")
            finally:
                await bot.session.close()

    return web.json_response({"ok": True})


async def pay_return(request: web.Request) -> web.Response:
    """
    Страница возврата после оплаты (return_url в create_invoice).
    Можно передавать payment_id в параметрах (?payment_id=...),
    тогда мы покажем текущий статус.
    """
    payment_id: Optional[str] = request.query.get("payment_id")
    if not payment_id:
        # YooKassa не всегда возвращает id — просто даём инструкцию.
        return _html(
            "Возврат после оплаты",
            "Спасибо! Если оплата прошла — подписка активируется автоматически.",
            "<p>Вы можете закрыть эту страницу и вернуться в Telegram.</p>"
            "<p class='warn'>Если подписка не активировалась в течение пары минут, нажмите «Проверить оплату» в боте.</p>"
        )

    try:
        status = fetch_status(payment_id)
    except Exception:
        status = "unknown"

    content = [
        f"<p>Платёж: <code>{payment_id}</code></p>",
        f"<p>Текущий статус: <b>{status}</b></p>",
        "<p>Вернитесь в Telegram — бот завершит настройку автоматически.</p>",
        "<a class='btn' href='https://t.me/{}'>Открыть Telegram</a>".format("RepBoostBot")
    ]
    return _html("Статус платежа", "Статус платежа", "\n".join(content))


async def pay_success(request: web.Request) -> web.Response:
    return _html(
        "Оплата успешна",
        "✅ Платёж успешно выполнен",
        "<p>Можете закрыть страницу и вернуться в Telegram. Подписка активируется автоматически.</p>"
    )


async def pay_fail(request: web.Request) -> web.Response:
    return _html(
        "Оплата не выполнена",
        "❌ Платёж не выполнен",
        "<p>Если возникла ошибка — попробуйте ещё раз в боте или выберите ручную оплату.</p>"
    )


def build_app() -> web.Application:
    app = web.Application()
    # Webhook от YooKassa
    app.router.add_post("/yookassa/webhook", yookassa_webhook)
    # Витринные страницы
    app.router.add_get("/pay/return", pay_return)
    app.router.add_get("/pay/success", pay_success)
    app.router.add_get("/pay/fail", pay_fail)
    return app
