import logging
from worker.services.homework_check_service import handle_homework_check

async def handle_check_homework(task: dict) -> dict:
    """
    Проверка домашнего задания — отправка текста на ревью с генерацией LaTeX.
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

    try:
        # Используем новый сервис для проверки ДЗ
        result = await handle_homework_check({
            "task_id": task_id,
            "text": text
        })
        
        if result.get("type") == "error":
            return result
        
        # Возвращаем LaTeX код для компиляции в боте
        latex_content = result.get("latex_content", "")
        if latex_content:
            return {
                "type": "homework_check",
                "task_id": task_id,
                "original_text": text,
                "check_result": result.get("check_result", ""),
                "latex_content": latex_content
            }
        else:
            return {
                "type": "error",
                "message": "Не удалось получить результат проверки"
            }
            
    except Exception as e:
        logging.exception("Ошибка в check_homework")
        return {
            "type": "error",
            "message": f"Ошибка при проверке ДЗ: {e}"
        }