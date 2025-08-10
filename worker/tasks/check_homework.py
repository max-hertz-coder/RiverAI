# worker/check_homework.py
import json
import logging
from typing import Dict, Any, List

from worker.services.homework_check_service import build_pdf_report
from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)


async def _gpt_check(text: str, refine: str | None = None) -> Dict[str, Any]:
    """
    Запрашиваем у GPT строго структурированный JSON с тремя полями.
    Если JSON распарсить не удаётся — даём безопасный фолбэк.
    """
    sys = (
        "Вы — преподаватель. Проверьте текст домашней работы, найдите ошибки "
        "и дайте рекомендации. Ответ верните в формате JSON с ключами:\n"
        "overview (строка), errors (массив строк), recommendations (массив строк).\n"
        "Пишите по-русски. Без лишних ключей."
    )
    user = f"Текст ДЗ:\n{text}"
    if refine:
        user += f"\n\nПравки/уточнения пользователя:\n{refine}"

    try:
        resp = await chat_with_gpt(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1200,
            response_format="json",  # если в обёртке поддерживается
        )
        raw = resp.get("text") or resp.get("content") or ""
        data = json.loads(raw)
        overview = str(data.get("overview", "") or "").strip()
        errors = [str(x).strip() for x in (data.get("errors") or []) if str(x).strip()]
        recs = [str(x).strip() for x in (data.get("recommendations") or []) if str(x).strip()]
        if not (overview or errors or recs):
            raise ValueError("empty json result")
        return {"overview": overview, "errors": errors, "recommendations": recs}
    except Exception:
        logger.warning("Fallback: plain analysis for homework check")
        # Фолбэк: всё в overview
        return {
            "overview": "Автоанализ неструктурирован. Проверьте корректность входных данных.",
            "errors": [],
            "recommendations": [],
        }


async def handle_check_homework(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Унифицированный обработчик задачи 'check_homework'.
    Возвращает dict с type='homework_check', file (base64) — при успехе.
    """
    try:
        text = (task.get("text") or "").strip()
        refine = (task.get("refine") or "").strip() or None
        if not text:
            return {"type": "error", "message": "Пустой текст для проверки."}

        gpt_result = await _gpt_check(text, refine)

        payload = {
            **gpt_result,
            "fallback_text": text,
        }
        result = await build_pdf_report(payload)
        if "task_id" in task:
            result["task_id"] = task["task_id"]
        return result

    except Exception as e:
        logger.exception("Ошибка в handle_check_homework")
        return {"type": "error", "message": f"Ошибка при проверке ДЗ: {e}"}
