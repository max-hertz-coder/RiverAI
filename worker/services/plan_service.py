# worker/services/plan_service.py
import logging
from worker.services.gpt_service import chat_with_gpt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Вы — опытный преподаватель. Составьте краткий индивидуальный учебный план "
    "для школьника или студента на основе описания запроса. "
    "План должен быть понятен родителям и ученику. "
    "Дайте 3–7 пунктов со сжатыми пояснениями, без формальностей."
)


async def handle_plan(task: dict) -> dict:
    task_id = task.get("task_id")
    description = (task.get("description") or task.get("prompt") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    if not description:
        return {"type": "error", "message": "Описание плана не указано."}

    try:
        resp = await chat_with_gpt(
            messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                      {"role": "user", "content": description}],
            temperature=0.3,
            max_tokens=800,
        )
        text = resp.get("text", "").strip()
        if text.startswith("```") and text.endswith("```"):
            text = text.strip("`\n")

        return {
            "type": "plan",
            "task_id": task_id,
            "plan_text": text,
            "prompt_tokens": int(resp.get("prompt_tokens", 0)),
            "completion_tokens": int(resp.get("completion_tokens", 0)),
        }
    except Exception as e:
        logger.exception("Ошибка при генерации плана")
        return {"type": "error", "task_id": task_id, "message": f"Ошибка при генерации плана: {e}"}
