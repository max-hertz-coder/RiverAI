import logging
import random
import asyncio
from openai import AsyncOpenAI
from worker import config

# Инициализация OpenAI клиента (рандомный ключ)
def _get_openai_client():
    key = random.choice(config.OPENAI_API_KEYS)
    return AsyncOpenAI(api_key=key)

async def chat_with_gpt(messages: list[dict], temperature=0.7, max_tokens=1000) -> str:
    """
    Универсальный вызов GPT (chat-based).
    """
    client = _get_openai_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.exception("Ошибка в chat_with_gpt")
        raise e