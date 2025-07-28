# worker/services/gpt_service.py

import os
import asyncio
from openai import OpenAI
from .generation_service import _system_prompts, _sync_call

# Инициализация клиента OpenAI (новый SDK 1.x)
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

async def generate_raw_tasks(prompt: str) -> str:
    """
    Генерация необработанных задач по системному промпту "tasks"
    """
    return await asyncio.to_thread(_sync_call, prompt, "tasks")

async def generate_raw_solutions(tasks: str) -> str:
    """
    Генерация необработанных решений по системному промпту "solutions"
    """
    return await asyncio.to_thread(_sync_call, tasks, "solutions")

async def ask_gpt(conversation: list[dict]) -> str:
    """
    Свободный режим общения с GPT: принимает список сообщений
    в формате OpenAI Chat API и возвращает ответ.
    """
    def sync_call():
        response = client.chat.completions.create(
            model="gpt-4",
            messages=conversation,
            temperature=0.5,
            max_tokens=1500
        )
        return response.choices[0].message.content.strip()

    return await asyncio.to_thread(sync_call)
