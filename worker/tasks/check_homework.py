import logging
from worker.services.gpt_service import chat_with_gpt

async def handle_check_homework(task: dict) -> dict:
    """
    Проверка домашнего задания — отправка текста на ревью.
    """
    task_id = task.get("task_id")
    text = task.get("text", "").strip()

    if not task_id:
        return {
            "type": "error",
            "message": "Отсутствует task_id."
        }

    if not text:
        return {
            "type": "error",
            "message": "❌ Не передан текст для проверки"
        }

    system_prompt = (
        "Вы — опытный преподаватель. Проверьте домашнюю работу ниже, найдите ошибки и дайте комментарии, "
        "покажите, что нужно исправить."
    )

    try:
        answer = await chat_with_gpt(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.0,
            max_tokens=1500
        )
        return {
            "type": "check",
            "report_text": answer
        }
    except Exception as e:
        logging.exception("Ошибка в check_homework")
        return {
            "type": "error",
            "message": f"GPT error: {e}"
        }