# bot_app/rabbit.py — ИТОГОВЫЙ (исправление TTL и падений при declare)

import os
import base64
import json
import logging
from typing import Any, Dict, Optional

import aiormq
import aio_pika
from aio_pika import DeliveryMode, Message
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from bot_app import config, database
from bot_app.keyboards.chat_menu import result_plan_kb, result_check_kb
from bot_app.keyboards.main_menu import back_button
from common.redis_utils import (
    get_context_by_task_id,
    cleanup_task_context,
    save_last_solutions_file,
)

logger = logging.getLogger(__name__)

_channel: Optional[aio_pika.Channel] = None

async def _get_channel() -> aio_pika.Channel:
    global _channel
    if _channel and not _channel.is_closed:
        return _channel
    conn = await aio_pika.connect_robust(config.RABBITMQ_AMQP_URL())
    _channel = await conn.channel()
    await _channel.set_qos(prefetch_count=16)
    logger.info("✅ RabbitMQ channel ready (bot)")
    return _channel

async def publish_task(payload: Dict[str, Any], routing_key: Optional[str] = None) -> None:
    ch = await _get_channel()
    rk = routing_key or config.TASK_QUEUE
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await ch.default_exchange.publish(
        Message(body=body, content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT),
        routing_key=rk,
    )
    logger.info("➡️  Task published to %s", rk)

async def publish_result(payload: Dict[str, Any], routing_key: Optional[str] = None) -> None:
    ch = await _get_channel()
    rk = routing_key or config.RESULT_QUEUE
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await ch.default_exchange.publish(
        Message(body=body, content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT),
        routing_key=rk,
    )
    logger.info("➡️  Result published to %s", rk)

async def pending_tasks() -> int:
    ch = await _get_channel()
    q = await ch.declare_queue(config.TASK_QUEUE, durable=True, passive=True)
    return q.declaration_result.message_count or 0

async def handle_result_payload(bot: Bot, data: Dict[str, Any]) -> None:
    task_id = data.get("task_id")
    if not task_id:
        logger.warning("⚠️ В результате нет task_id")
        return

    context = await get_context_by_task_id(task_id)
    if not context:
        logger.warning("⚠️ Контекст не найден для task_id=%s", task_id)
        return

    user_id: Optional[int] = context.get("user_id")
    student_id: Optional[int] = context.get("student_id")
    result_type: str = data.get("type") or ""

    if not user_id or not result_type:
        logger.warning("⚠️ Отсутствует user_id или type в результате")
        return

    try:
        if result_type in {"chat", "chat_gpt"}:
            text = data.get("answer") or data.get("gpt_response") or "(нет ответа)"
            await bot.send_message(user_id, text, reply_markup=back_button("← Назад", "back:main"))

        elif result_type == "plan":
            plan_text = data.get("plan_text", "(пусто)")
            await bot.send_message(user_id, f"📄 План:\n{plan_text}", reply_markup=result_plan_kb(student_id))

        elif result_type == "tasks":
            prompt = (data.get("prompt") or "").strip()
            raw = (data.get("tasks_text") or "").strip()

            parts = []
            if prompt:
                parts.append(f"🔄 Финальный запрос для генерации:\n{prompt}")
            if raw:
                parts.append(f"📝 Задания:\n\n{raw}")
            parts.append("❓ Всё ли устраивает?")
            text = "\n\n".join(parts)

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Всё норм", callback_data="tasks_ok"),
                InlineKeyboardButton(text="✏️ Переделать", callback_data=f"refine_tasks:{student_id or 0}"),
            ]])
            await bot.send_message(user_id, text, reply_markup=kb)

            t_b64 = data.get("tasks_pdf_b64") or data.get("file_tasks")
            s_b64 = data.get("solutions_pdf_b64") or data.get("file_solutions")

            if t_b64:
                t_bytes = base64.b64decode(t_b64)
                await bot.send_document(user_id, BufferedInputFile(t_bytes, "Tasks.pdf"), caption="📎 PDF: Задания")
            if s_b64:
                s_bytes = base64.b64decode(s_b64)
                await bot.send_document(user_id, BufferedInputFile(s_bytes, "Solutions.pdf"), caption="📎 PDF: Решения")
                try:
                    await save_last_solutions_file(user_id, s_b64)
                except Exception:
                    logger.exception("Не удалось сохранить Solutions.pdf в Redis")

        elif result_type == "check":
            report = data.get("report_text", "(нет отчёта)")
            await bot.send_message(user_id, f"✔️ Результаты проверки:\n{report}", reply_markup=result_check_kb(student_id))
            file_b64 = data.get("file")
            if file_b64:
                pdf_bytes = base64.b64decode(file_b64)
                await bot.send_document(user_id, BufferedInputFile(pdf_bytes, "Homework_Report.pdf"), caption="📎 Отчёт в PDF")

        elif result_type == "homework_check":
            report_text = data.get("check_result", "(нет отчёта)")
            file_b64 = data.get("file")
            if file_b64:
                pdf_bytes = base64.b64decode(file_b64)
                await bot.send_document(user_id, BufferedInputFile(pdf_bytes, "Homework_Check.pdf"), caption="📄 Результат проверки ДЗ")
            else:
                if len(report_text) > 4000:
                    report_text = report_text[:4000] + "\n\n… (ответ обрезан)"
                await bot.send_message(user_id, f"📋 Результат проверки ДЗ:\n\n{report_text}",
                                       reply_markup=result_check_kb(student_id))

        elif result_type == "ocr":
            user_prompt = (data.get("prompt") or "").strip()
            ocr_text = (data.get("text") or "").strip()
            if not ocr_text:
                await bot.send_message(user_id, "❌ Не удалось распознать текст на изображении.")
            else:
                final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text
                await bot.send_message(user_id, f"🔄 Финальный запрос для генерации:\n{final_prompt}")
                try:
                    from bot_app.task_utils import create_task_with_context
                    task = {"type": "generate_tasks", "user_id": user_id, "student_id": student_id, "prompt": final_prompt}
                    task_with_ctx = await create_task_with_context(task)
                    await publish_task(task_with_ctx)
                    await bot.send_message(user_id, "🕔 Генерируются задания, ожидайте…")
                except Exception:
                    logger.exception("Не удалось отправить повторную задачу generate_tasks")
                    await bot.send_message(user_id, "⚠️ Не удалось запустить генерацию. Попробуйте ещё раз.")

        elif result_type == "error":
            error_msg = data.get("message", "Неизвестная ошибка")
            await bot.send_message(user_id, f"⚠️ Ошибка: {error_msg}")
            try:
                await bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Worker error (user {user_id}, task {task_id}): {error_msg}")
            except Exception:
                logger.exception("Не удалось уведомить админа")

        else:
            logger.warning("❓ Unknown result type: %s", result_type)

        # учёт токенов
        prompt_tokens = int(data.get("prompt_tokens") or data.get("input_tokens") or 0)
        gen_tokens = int(data.get("completion_tokens") or data.get("output_tokens") or 0)
        try:
            await database.db.increment_usage(user_id)
            await database.db.increment_token_usage(user_id, prompt_tokens, gen_tokens)
            if student_id:
                await database.db.increment_student_token_usage(student_id, prompt_tokens, gen_tokens)
        except Exception:
            logger.exception("Не удалось обновить usage/token usage")

    finally:
        try:
            await cleanup_task_context(task_id)
        except Exception:
            logger.exception("Ошибка очистки контекста task_id=%s", task_id)

# ============ FIX: TTL mismatch ============
async def start_result_consumer(bot: Bot) -> None:
    """
    Сначала пассивно открываем очередь (не меняя её аргументы).
    Если её нет — создаём с TTL=900000 мс (или из ENV).
    Так избегаем PRECONDITION_FAILED при несовпадении x-message-ttl.
    """
    connection = await aio_pika.connect_robust(config.RABBITMQ_AMQP_URL())
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=8)

    ttl_ms = int(os.getenv("RABBITMQ_RESULT_TTL_MS", getattr(config, "RESULT_TTL_MS", 900000)))

    try:
        # 1) пробуем не изменять существующую очередь
        queue = await channel.declare_queue(config.RESULT_QUEUE, durable=True, passive=True)
        logger.info("📥 Result consumer attached to existing queue '%s'", config.RESULT_QUEUE)
    except Exception as e:
        logger.warning("Result queue passive declare failed (%s). Creating with TTL=%s ms…", type(e).__name__, ttl_ms)
        # 2) создаём с тем же TTL, что уже настроен на брокере (дефолт 900000)
        args = {"x-message-ttl": ttl_ms}
        queue = await channel.declare_queue(config.RESULT_QUEUE, durable=True, arguments=args)
        logger.info("📥 Result consumer created queue '%s' with args=%s", config.RESULT_QUEUE, args)

    async with queue.iterator() as q:
        async for message in q:
            async with message.process():
                try:
                    payload = json.loads(message.body)
                except Exception:
                    logger.exception("❌ Не удалось разобрать JSON результата")
                    continue
                try:
                    await handle_result_payload(bot, payload)
                except Exception as e:
                    logger.exception("🔴 Ошибка обработки результата: %s", e)
                    try:
                        await bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Ошибка обработки результата: {e}")
                    except Exception:
                        logger.exception("Не удалось уведомить админа")
