# bot_app/rabbit.py
import base64
import json
import logging
from typing import Any, Dict, Optional

import aio_pika
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


async def handle_result_payload(bot: Bot, data: Dict[str, Any]) -> None:
    """Единая логика обработки результата от воркера (AMQP/Redis)."""
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
        # Chat
        if result_type in {"chat", "chat_gpt"}:
            text = data.get("answer") or data.get("gpt_response") or "(нет ответа)"
            await bot.send_message(user_id, text, reply_markup=back_button("← Назад", "back:main"))

        # Study plan
        elif result_type == "plan":
            plan_text = data.get("plan_text", "(пусто)")
            await bot.send_message(user_id, f"📄 План:\n{plan_text}", reply_markup=result_plan_kb(student_id))

        # Generated tasks (PDF уже собраны воркером)
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
                    await save_last_solutions_file(user_id, s_b64)  # сохраним исходный base64
                except Exception:
                    logger.exception("Не удалось сохранить Solutions.pdf в Redis")

        # Homework check (старый формат)
        elif result_type == "check":
            report = data.get("report_text", "(нет отчёта)")
            await bot.send_message(user_id, f"✔️ Результаты проверки:\n{report}", reply_markup=result_check_kb(student_id))

            file_b64 = data.get("file")
            if file_b64:
                pdf_bytes = base64.b64decode(file_b64)
                await bot.send_document(user_id, BufferedInputFile(pdf_bytes, "Homework_Report.pdf"), caption="📎 Отчёт в PDF")

        # Homework check (новый формат: бот только отправляет готовый PDF)
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

        # OCR-only: перекидываем в generate_tasks
        elif result_type == "ocr":
            user_prompt = (data.get("prompt") or "").strip()
            ocr_text = (data.get("text") or "").strip()

            if not ocr_text:
                await bot.send_message(user_id, "❌ Не удалось распознать текст на изображении.")
            else:
                final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text
                await bot.send_message(user_id, f"🔄 Финальный запрос для генерации:\n{final_prompt}")

                try:
                    # ВАЖНО: путь импорта соответствует вашему проекту (файл bot_app/task_utils.py)
                    from bot_app.task_utils import create_task_with_context
                    task = {"type": "generate_tasks", "user_id": user_id, "student_id": student_id, "prompt": final_prompt}
                    task_with_ctx = await create_task_with_context(task)
                    conn = await aio_pika.connect_robust(config.RABBITMQ_AMQP_URL())
                    ch = await conn.channel()
                    await ch.default_exchange.publish(
                        aio_pika.Message(body=json.dumps(task_with_ctx).encode()),
                        routing_key=config.TASK_QUEUE,
                    )
                    await conn.close()
                    await bot.send_message(user_id, "🕔 Генерируются задания, ожидайте…")
                except Exception:
                    logger.exception("Не удалось отправить повторную задачу generate_tasks")
                    await bot.send_message(user_id, "⚠️ Не удалось запустить генерацию. Попробуйте ещё раз.")

        # Error
        elif result_type == "error":
            error_msg = data.get("message", "Неизвестная ошибка")
            await bot.send_message(user_id, f"⚠️ Ошибка: {error_msg}")
            try:
                await bot.send_message(config.ADMIN_CHAT_ID, f"🔴 Worker error (user {user_id}, task {task_id}): {error_msg}")
            except Exception:
                logger.exception("Не удалось уведомить админа")

        else:
            logger.warning("❓ Unknown result type: %s", result_type)

        # Учёт использования/токенов
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


async def start_result_consumer(bot: Bot) -> None:
    """Подключается к RESULT_QUEUE и обрабатывает входящие сообщения."""
    connection = await aio_pika.connect_robust(config.RABBITMQ_AMQP_URL())
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=8)

    queue = await channel.declare_queue(config.RESULT_QUEUE, durable=True)
    logger.info("📥 Result consumer started (queue=%s)", config.RESULT_QUEUE)

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
