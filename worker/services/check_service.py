import asyncio
import logging

from worker.services.gpt_service import ask_gpt

async def handle_check(task: dict) -> dict:
    """
    Проверка ДЗ: передаём распознанный текст (task["file_data"]) в GPT-модель.
    """
    # если нужно, распакуйте base64 и сохраните во временный файл, распознайте текст,
    # затем формируйте prompt для GPT
    description = task.get("description", "")
    system = {"role": "system", "content": "Вы — педагог; проверьте это домашнее задание и дайте отчёт:"}
    user   = {"role": "user",   "content": description}
    report = await ask_gpt([system, user])
    logging.info(f"[chat_service] Answer to queue: {report}")

    return {
        "type": "check_homework_result",
        "user_id": task["user_id"],
        "student_id": task["student_id"],
        "report_text": report
    }
