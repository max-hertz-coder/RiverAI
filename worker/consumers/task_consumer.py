import logging

from worker.services.ocr_service import handle_ocr, handle_ocr_and_generate
from worker.services.plan_service import handle_plan
from worker.services.tasks_service import handle_tasks
from worker.tasks.check_homework import handle_check_homework
from worker.services.chat_service import handle_chat
from worker.services.homework_check_service import handle_homework_check
from worker.services.chat_gpt_service import handle_chat_gpt
from common.redis_utils import clear_conversation

async def process_task_message(task: dict) -> dict | None:
    """
    Обрабатывает задачу из очереди task_queue и возвращает результат или None.
    """
    task_id = task.get("task_id")
    task_type = task.get("type")

    logging.info(f"🔧 Начинаем обработку задачи: task_id={task_id}, type={task_type}")
    logging.info(f"🔧 Полная задача: {task}")

    if not task_id:
        logging.error("🔴 Task missing task_id")
        return None

    try:
        if task_type == "ocr_and_generate":
            return await handle_ocr_and_generate(task)

        if task_type == "ocr":
            return await handle_ocr(task)

        if task_type == "ocr_and_check":
            # OCR + проверка ДЗ
            from worker.services.ocr_service import handle_ocr
            logging.info(f"🔧 Начинаем OCR для проверки ДЗ: task_id={task_id}")
            ocr_result = await handle_ocr(task)
            logging.info(f"🔧 OCR результат: {ocr_result}")
            
            if ocr_result.get("type") == "error":
                logging.error(f"🔴 OCR ошибка: {ocr_result}")
                return ocr_result
            
            # Теперь проверяем ДЗ
            check_task = {
                "task_id": task_id,
                "text": ocr_result.get("text", "")
            }
            logging.info(f"🔧 Отправляем на проверку ДЗ: text_length={len(check_task['text'])}")
            return await handle_check_homework(check_task)

        if task_type == "generate_plan":
            return await handle_plan(task)

        if task_type in ("generate_tasks", "generate_solutions"):
            logging.info(f"🔧 Вызываем handle_tasks для task_id={task_id}")
            result = await handle_tasks(task)
            logging.info(f"🔧 handle_tasks вернул: {type(result)} - {result}")
            return result

        if task_type == "check_homework":
            return await handle_check_homework(task)

        if task_type == "chat_gpt":
            return await handle_chat_gpt(task)

        if task_type in ("chat"):
            logging.info(f"🔧 Вызываем handle_chat для task_id={task_id}")
            result = await handle_chat(task)
            logging.info(f"🔧 handle_chat вернул: type={result.get('type') if result else 'None'}")
            return result

        if task_type == "end_chat":
            # Очищаем историю диалога
            # Получаем контекст из Redis для получения user_id и student_id
            from common.redis_utils import get_context_by_task_id
            context = await get_context_by_task_id(task_id)
            if context:
                user_id = context.get("user_id")
                student_id = context.get("student_id")
                if user_id and student_id:
                    await clear_conversation(user_id, student_id)
                    return {
                        "type": "chat",
                        "answer": "🗑️ Диалог очищен."
                    }
            return {
                "type": "chat",
                "answer": "🗑️ Диалог очищен."
            }

        logging.warning("Unknown task type: %s", task_type)

    except Exception as e:
        logging.exception(f"🔴 Error processing task {task_type} with task_id={task_id}: {e}")
        return {
            "type": "error",
            "message": "Внутренняя ошибка обработки задачи."
        }

    return None