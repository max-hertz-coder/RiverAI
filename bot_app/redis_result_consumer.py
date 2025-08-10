# bot_app/redis_result_consumer.py
import asyncio
import json
import logging
import base64
import html
import re
from typing import Any, Dict, Optional, Iterable, List

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

# === formatting helpers =======================================================

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODEBLOCK_RE = re.compile(r"```(.*?)```", flags=re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

def _mdish_to_html(text: str) -> str:
    """
    Простейший преобразователь "псевдо-markdown" → HTML,
    чтобы ответы выглядели красиво в Telegram (parse_mode=HTML).
    """
    if not isinstance(text, str):
        text = str(text)

    # Сначала экранируем HTML-символы
    text = html.escape(text)

    # Блочные код-блоки: ```...```
    def _codeblock_sub(m: re.Match) -> str:
        code = m.group(1)
        return f"<pre><code>{code}</code></pre>"

    text = _CODEBLOCK_RE.sub(_codeblock_sub, text)

    # Инлайн-код: `code`
    def _inline_code_sub(m: re.Match) -> str:
        code = m.group(1)
        return f"<code>{code}</code>"

    text = _INLINE_CODE_RE.sub(_inline_code_sub, text)

    # Жирный шрифт: **bold**
    text = _BOLD_RE.sub(r"<b>\1</b>", text)

    # Преобразуем списки на уровне начала строки "- " → "• "
    lines: List[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("- "):
            # сохраняем исходные отступы, меняем маркер
            prefix = line[: len(line) - len(line.lstrip())]
            lines.append(f"{prefix}• {line.lstrip()[2:]}")
        else:
            lines.append(line)
    return "\n".join(lines)


def _chunk_text(text: str, limit: int = 3900) -> Iterable[str]:
    """
    Telegram ограничивает длину ~4096. Режем безопасно (оставляем запас под HTML-теги).
    Стараемся делить по пустым строкам/точкам.
    """
    if len(text) <= limit:
        yield text
        return

    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        # попытаться отрезать по ближайшему разделителю
        cut = text.rfind("\n\n", start, end)
        if cut == -1:
            cut = text.rfind("\n", start, end)
        if cut == -1:
            cut = text.rfind(". ", start, end)
        if cut == -1 or cut <= start + 500:  # чтобы не было уж слишком мелких кусков
            cut = end
        chunk = text[start:cut].rstrip()
        if chunk:
            yield chunk
        start = cut


async def _safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            **kwargs,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить сообщение пользователю %s", chat_id)


async def _send_pretty_text(bot: Bot, chat_id: int, raw_text: str, **kwargs) -> None:
    html_text = _mdish_to_html(raw_text or "")
    for chunk in _chunk_text(html_text):
        await _safe_send_message(bot, chat_id, chunk, **kwargs)


def _trim(text: str, limit: int = 4000) -> str:
    if not isinstance(text, str):
        text = str(text)
    return text if len(text) <= limit else (text[:limit] + "\n\n… (текст обрезан)")


def _b64_to_bytes(s: Optional[str]) -> Optional[bytes]:
    if not s:
        return None
    try:
        # поддержка URL-safe и отсутствие padding
        s_padded = s + "=" * ((4 - len(s) % 4) % 4)
        try:
            return base64.b64decode(s_padded, validate=True)
        except Exception:
            return base64.urlsafe_b64decode(s_padded)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось декодировать base64")
        return None


# === core =====================================================================

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

    logger.info(
        "📥 Обрабатываем результат: task_id=%s, type=%s, user_id=%s",
        task_id, result_type, user_id,
    )

    try:
        if result_type == "tasks":
            t_b64 = result_data.get("tasks_pdf_b64") or result_data.get("file_tasks")
            s_b64 = result_data.get("solutions_pdf_b64") or result_data.get("file_solutions")

            t_bytes = _b64_to_bytes(t_b64)
            s_bytes = _b64_to_bytes(s_b64)

            if t_bytes:
                await bot.send_document(
                    user_id,
                    BufferedInputFile(t_bytes, "Tasks.pdf"),
                    caption="📎 Задания",
                )
            else:
                await _send_pretty_text(bot, user_id, "❌ Не удалось создать PDF с заданиями")

            if s_bytes:
                await bot.send_document(
                    user_id,
                    BufferedInputFile(s_bytes, "Solutions.pdf"),
                    caption="📎 Решения",
                )
                # сохраним исходный base64 для «✏️ Переделать»
                await save_last_solutions_file(user_id, s_b64 or "")
            else:
                await _send_pretty_text(bot, user_id, "❌ Не удалось создать PDF с решениями")

            kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Всё отлично", callback_data="tasks_ok"),
                    InlineKeyboardButton(text="✏️ Переделать", callback_data="refine_tasks"),
                ]]
            )
            await _send_pretty_text(bot, user_id, "❓ Всё ли устраивает?", reply_markup=kb)

        elif result_type == "chat":
            text = result_data.get("answer", "(нет ответа)")
            await _send_pretty_text(
                bot,
                user_id,
                text,
                reply_markup=back_button("← Назад", "back:main"),
            )

        elif result_type == "plan":
            plan_text = result_data.get("plan_text", "(пусто)")
            await _send_pretty_text(
                bot,
                user_id,
                f"📄 План:\n{plan_text}",
                reply_markup=result_plan_kb(student_id),
            )

        elif result_type == "check":
            report = result_data.get("report_text", "(нет отчёта)")
            await _send_pretty_text(
                bot,
                user_id,
                f"✔️ Результаты проверки:\n{report}",
                reply_markup=result_check_kb(student_id),
            )
            file_b64 = result_data.get("file")
            pdf_bytes = _b64_to_bytes(file_b64)
            if pdf_bytes:
                await bot.send_document(
                    user_id,
                    BufferedInputFile(pdf_bytes, "Homework_Report.pdf"),
                    caption="📎 Отчёт в PDF",
                )

        elif result_type == "homework_check":
            report_text = result_data.get("check_result", "(нет отчёта)")
            file_b64 = result_data.get("file")
            pdf_bytes = _b64_to_bytes(file_b64)
            if pdf_bytes:
                await bot.send_document(
                    user_id,
                    BufferedInputFile(pdf_bytes, "Homework_Check.pdf"),
                    caption="📄 Результат проверки ДЗ",
                )
            else:
                await _send_pretty_text(
                    bot,
                    user_id,
                    f"📋 Результат проверки ДЗ:\n\n{report_text}",
                    reply_markup=back_button("← Назад", "back:main"),
                )

        elif result_type == "chat_gpt":
            answer = result_data.get("gpt_response", "(нет ответа)")
            await _send_pretty_text(
                bot,
                user_id,
                answer,
                reply_markup=back_button("← Назад", "back:main"),
            )

        elif result_type == "error":
            error_msg = result_data.get("message", "Неизвестная ошибка")
            logger.error(
                "🔴 Получена ошибка от worker (task %s, user %s): %s",
                task_id, user_id, error_msg,
            )
            await _send_pretty_text(
                bot,
                user_id,
                "⚠️ Произошла ошибка при обработке результата. Попробуйте позже.",
            )

        else:
            logger.warning("❓ Unknown result type: %s", result_type)

        # учёт токенов/использования (мягко, без падений)
        try:
            prompt_tokens = int(
                result_data.get("prompt_tokens")
                or result_data.get("input_tokens")
                or 0
            )
            gen_tokens = int(
                result_data.get("completion_tokens")
                or result_data.get("output_tokens")
                or 0
            )
            if result_type in ("chat", "chat_gpt", "plan", "tasks", "check", "homework_check"):
                await database.db.increment_usage(user_id)
                await database.db.increment_token_usage(user_id, prompt_tokens, gen_tokens)
                if student_id:
                    await database.db.increment_student_token_usage(
                        student_id, prompt_tokens, gen_tokens
                    )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Не удалось обновить usage/token usage (user %s, student %s)",
                user_id, student_id,
            )

    except Exception as e:  # noqa: BLE001
        logger.exception("🔴 Ошибка обработки результата (task %s): %s", task_id, e)
        await _send_pretty_text(
            bot,
            user_id,
            "⚠️ Непредвиденная ошибка при обработке результата.",
        )
    finally:
        try:
            await cleanup_task_context(task_id)
        except Exception as cleanup_error:  # noqa: BLE001
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
                except Exception:  # noqa: BLE001
                    logger.exception("Ошибка обработки результата из Redis (%s)", key)
            await asyncio.sleep(poll_interval)
        except Exception as e:  # noqa: BLE001
            logger.exception("🔴 Ошибка в цикле Redis result poller: %s", e)
            await asyncio.sleep(max(5.0, poll_interval))
