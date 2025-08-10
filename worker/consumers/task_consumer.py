# worker/task_consumer.py
import logging

from worker.services.ocr_service import handle_ocr, handle_ocr_and_generate
from worker.services.plan_service import handle_plan
from worker.services.tasks_service import handle_tasks
from worker.tasks.check_homework import handle_check_homework
from worker.services.chat_service import handle_chat
from worker.services.homework_check_service import handle_homework_check
from common.redis_utils import clear_conversation

logging.info(f"handle_chat импортирован: {handle_chat}")
logging.info(f"Тип handle_chat: {type(handle_chat)}")

async def process_task_message(task: dict) -> dict | None:
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
            logging.info(f"🔧 OCR для проверки ДЗ: task_id={task_id}")
            ocr_result = await handle_ocr(task)
            logging.info(f"🔧 OCR результат: {ocr_result}")

            if ocr_result.get("type") == "error":
                logging.error(f"🔴 OCR ошибка: {ocr_result}")
                return ocr_result

            check_task = {"task_id": task_id, "text": ocr_result.get("text", "")}
            logging.info(f"🔧 Отправляем на проверку ДЗ (len={len(check_task['text'])})")
            return await handle_homework_check(check_task)

        if task_type == "generate_plan":
            return await handle_plan(task)

        if task_type in {"generate_tasks", "generate_solutions"}:
            logging.info(f"🔧 Вызываем handle_tasks для task_id={task_id}")
            result = await handle_tasks(task)
            logging.info(f"🔧 handle_tasks вернул: {type(result)} - {result}")
            return result

        if task_type == "check_homework":
            return await handle_homework_check(task)

        if task_type == "chat":
            logging.info(f"Обрабатываем чат: task_id={task_id}")
            try:
                result = await handle_chat(task)
                logging.info(f"Результат чата: {result.get('type')}")
                return result
            except Exception as e:
                logging.exception(f"Ошибка в чате: {e}")
                return {"type": "error", "message": f"Ошибка в чате: {str(e)}"}

        if task_type == "end_chat":
            from common.redis_utils import get_context_by_task_id
            context = await get_context_by_task_id(task_id)
            if context:
                user_id = context.get("user_id")
                student_id = context.get("student_id")
                if user_id and student_id:
                    await clear_conversation(user_id, student_id)
                    return {"type": "chat", "answer": "🗑️ Диалог очищен."}
            return {"type": "chat", "answer": "🗑️ Диалог очищен."}

        logging.warning("Unknown task type: %s", task_type)
        return {"type": "error", "message": f"Неизвестный тип задачи: {task_type}"}

    except Exception as e:
        logging.exception(f"🔴 Error processing task {task_type} with task_id={task_id}: {e}")
        return {"type": "error", "message": "Внутренняя ошибка обработки задачи."}
