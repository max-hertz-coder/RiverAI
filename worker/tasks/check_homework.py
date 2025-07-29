import logging
from worker.services.gpt_service import chat_with_gpt

async def handle_check_homework(task: dict) -> dict:
    """
    Проверка домашнего задания — отправка текста на ревью.
    """
    user_id = task["user_id"]
    student_id = task["student_id"]
    text = task.get("text", "").strip()

    if not text:
        return {
            "type": "error",
            "user_id": user_id,
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
            "user_id": user_id,
            "student_id": student_id,
            "report_text": answer
        }
    except Exception as e:
        logging.exception("Ошибка в check_homework")
        return {
            "type": "error",
            "user_id": user_id,
            "message": f"GPT error: {e}"
        }