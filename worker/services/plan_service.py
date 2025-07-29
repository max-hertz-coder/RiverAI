# worker/services/plan_service.py

import os
import asyncio
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_system_prompt = (
    "Вы — опытный преподаватель. Составьте краткий индивидуальный учебный план "
    "для школьника или студента на основе описания запроса. "
    "План должен быть понятен родителям и ученику, без избыточных формальностей. "
    "Подавайте его в виде списка из 3–7 пунктов, с краткими пояснениями."
)

def _sync_generate_plan(prompt: str) -> str:
    """
    Генерация текста учебного плана.
    """
    messages = [
        {"role": "system", "content": _system_prompt},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=800
    )
    text = response.choices[0].message.content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
    return text

async def handle_plan(task: dict) -> dict:
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    prompt = task.get("prompt", "").strip()

    if not prompt:
        return {
            "type": "error",
            "user_id": user_id,
            "message": "Описание плана не указано."
        }

    try:
        plan_text = await asyncio.to_thread(_sync_generate_plan, prompt)
    except Exception as e:
        return {
            "type": "error",
            "user_id": user_id,
            "message": f"Ошибка при генерации плана: {e}"
        }

    return {
        "type": "plan",
        "user_id": user_id,
        "student_id": student_id,
        "plan_text": plan_text.strip()
    }