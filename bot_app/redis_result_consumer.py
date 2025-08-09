# bot_app/redis_result_consumer.py
import asyncio
import json
import logging
import base64
from typing import Any, Dict, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from bot_app import database
from bot_app.keyboards.chat_menu import result_plan_kb, result_check_kb
from bot_app.keyboards.main_menu import back_button
from common.redis_utils import (
    _get_client,
    get_context_by_task_id,
    cleanup_task_context,
    save_last_solutions_file,
)

logger = logging.getLogger(__name__)


async def _safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        logger.exception("Не удалось отправить сообщение пользователю %s", chat_id)


def _trim(text: str, limit: int = 4000) -> str:
    if not isinstance(text, str):
        text = str(text)
    return text if len(text) <= limit else (text[:limit] + "\n\n… (текст обрезан)")


async def process_redis_result(result_data: Dict[str, Any], bot: Bot):
    """
    Обработка результата из Redis:
      - tasks: принимает tasks_pdf_b64 / solutions_pdf_b64 → отправляет PDF
      - homework_check: принимает file(b64) → отправляет PDF (или текст)
      - chat/chat_gpt/plan/check/error — текстовые ветки
    """
    task_id = result_data.get("task_id")
    if not task_id:
        logger.warning("⚠️ В результате нет task_id: %s", result_data)
        return

    context = await get_context_by_task_id(task_id)
    if not context:
        logger.warning("⚠️ Контекст не найден для task_id=%s", task_id)
        return

    user_id: Optional[int] = context.get("user_id")
    student_id: Optional[int] = context.get("student_id")
    result_type: Optional[str] = result_data.get("type")

    if not user_id or not result_type:
        logger.warning("⚠️ В результате нет user_id или type (task_id=%s)", task_id)
        return

    logger.info("📥 Обрабатываем результат: task_id=%s, type=%s, user_id=%s",
                task_id, result_type, user_id)

    try:
        if result_type == "tasks":
            t_b64 = result_data.get("tasks_pdf_b64") or result_data.get("file_tasks")
            s_b64 = result_data.get("solutions_pdf_b64") or result_data.get("file_solutions")

            if t_b64:
                t_bytes = base64.b64decode(t_b64)
                await bot.send_document(user_id, BufferedInputFile(t_bytes, "Tasks.pdf"), caption="📎 Задания")
            else:
                await _safe_send_message(bot, user_id, "❌ Не удалось создать PDF с заданиями")

            if s_b64:
                s_bytes = base64.b64decode(s_b64)
                await bot.send_document(user_id, BufferedInputFile(s_bytes, "Solutions.pdf"), caption="📎 Решения")
                # сохраним исходный base64 для «✏️ Переделать»
                await save_last_solutions_file(user_id, s_b64)
            else:
                await _safe_send_message(bot, user_id, "❌ Не удалось создать PDF с решениями")

            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Всё отлично", callback_data="tasks_ok"),
                InlineKeyboardButton(text="✏️ Переделать", callback_data="refine_tasks"),
            ]])
            await _safe_send_message(bot, user_id, "❓ Всё ли устраивает?", reply_markup=kb)

        elif result_type == "chat":
            text = result_data.get("answer", "(нет ответа)")
            await _safe_send_message(bot, user_id, _trim(text), reply_markup=back_button("← Назад", "back:main"))

        elif result_type == "plan":
            plan_text = result_data.get("plan_text", "(пусто)")
            await _safe_send_message(bot, user_id, f"📄 План:\n{_trim(plan_text)}", reply_markup=result_plan_kb(student_id))

        elif result_type == "check":
            report = result_data.get("report_text", "(нет отчёта)")
            await _safe_send_message(bot, user_id, f"✔️ Результаты проверки:\n{_trim(report)}", reply_markup=result_check_kb(student_id))
            file_b64 = result_data.get("file")
            if file_b64:
                pdf_bytes = base64.b64decode(file_b64)
                await bot.send_document(user_id, BufferedInputFile(pdf_bytes, "Homework_Report.pdf"), caption="📎 Отчёт в PDF")

        elif result_type == "homework_check":
            report_text = result_data.get("check_result", "(нет отчёта)")
            file_b64 = result_data.get("file")
            if file_b64:
                pdf_bytes = base64.b64decode(file_b64)
                await bot.send_document(user_id, BufferedInputFile(pdf_bytes, "Homework_Check.pdf"), caption="📄 Результат проверки ДЗ")
            else:
                await _safe_send_message(bot, user_id, f"📋 Результат проверки ДЗ:\n\n{_trim(report_text)}", reply_markup=back_button("← Назад", "back:main"))

        elif result_type == "chat_gpt":
            answer = result_data.get("gpt_response", "(нет ответа)")
            await _safe_send_message(bot, user_id, _trim(answer), reply_markup=back_button("← Назад", "back:main"))

        elif result_type == "error":
            error_msg = result_data.get("message", "Неизвестная ошибка")
            logger.error("🔴 Получена ошибка от worker (task %s, user %s): %s", task_id, user_id, error_msg)
            await _safe_send_message(bot, user_id, "⚠️ Произошла ошибка при обработке результата. Попробуйте позже.")

        else:
            logger.warning("❓ Unknown result type: %s", result_type)

        # учёт токенов/использования
        try:
            prompt_tokens = int(result_data.get("prompt_tokens") or result_data.get("input_tokens") or 0)
            gen_tokens = int(result_data.get("completion_tokens") or result_data.get("output_tokens") or 0)
            if result_type in ("chat", "chat_gpt", "plan", "tasks", "check", "homework_check"):
                await database.db.increment_usage(user_id)
                await database.db.increment_token_usage(user_id, prompt_tokens, gen_tokens)
                if student_id:
                    await database.db.increment_student_token_usage(student_id, prompt_tokens, gen_tokens)
        except Exception:
            logger.exception("Не удалось обновить usage/token usage (user %s, student %s)", user_id, student_id)

    except Exception as e:
        logger.exception("🔴 Ошибка обработки результата (task %s): %s", task_id, e)
        await _safe_send_message(bot, user_id, "⚠️ Непредвиденная ошибка при обработке результата.")
    finally:
        try:
            await cleanup_task_context(task_id)
        except Exception as cleanup_error:
            logger.error("🔴 Ошибка очистки контекста task_id=%s: %s", task_id, cleanup_error)


async def consume_redis_results(bot: Bot, poll_interval: float = 2.0) -> None:
    logger.info("🔧 Запускаем проверку результатов в Redis… (interval=%.1fs)", poll_interval)
    while True:
        try:
            client = _get_client()
            result_keys = await client.keys("result:*")
            for key in result_keys:
                try:
                    raw = await client.get(key)
                    if not raw:
                        continue
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8", errors="ignore")
                    result_data = json.loads(raw)
                    await process_redis_result(result_data, bot)
                    await client.delete(key)
                except Exception:
                    logger.exception("Ошибка обработки результата из Redis (%s)", key)
            await asyncio.sleep(poll_interval)
        except Exception as e:
            logger.exception("🔴 Ошибка в цикле Redis result poller: %s", e)
            await asyncio.sleep(max(5.0, poll_interval))
