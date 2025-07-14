# worker/consumers/task_consumer.py
from worker.tasks import generate_plan, generate_tasks, check_homework, chat_gpt

async def process_task_message(task: dict):
    task_type = task.get("type")
    if task_type == "generate_plan":
        return await generate_plan.handle_generate_plan(task)
    elif task_type == "generate_tasks":
        return await generate_tasks.handle_generate_tasks(task)
    elif task_type == "check_homework":
        return await check_homework.handle_check_homework(task)
    elif task_type == "chat_gpt":
        return await chat_gpt.handle_chat_gpt(task)
    elif task_type == "end_chat":
        # End chat context (clear conversation in Redis)
        await chat_gpt.handle_end_chat(task)
        return None  # No direct response to user needed for ending chat
    else:
        # Unknown task type, respond with error (optional)
        if "user_id" in task:
            return {"type": "error", "user_id": task["user_id"], "message": "Unknown task type"}
    return None
