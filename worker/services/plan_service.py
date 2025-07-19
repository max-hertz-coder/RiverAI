import asyncio
from worker.services.gpt_service import ask_gpt

async def handle_plan(task: dict) -> dict:
    """
    Генерация учебного плана — вызываем GPT напрямую по описанию.
    """
    prompt = task["description"]
    # Системное сообщение можно вынести в константы
    system = {"role": "system", "content": "Вы — педагог; составьте учебный план:"}
    user    = {"role": "user",   "content": prompt}
    plan_text = await ask_gpt([system, user])

    return {
        "type": "plan",
        "user_id": task["user_id"],
        "student_id": task["student_id"],
        "plan_text": plan_text
    }
