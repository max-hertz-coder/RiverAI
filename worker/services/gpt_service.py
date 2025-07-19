# /opt/RiverAI/worker/services/gpt_service.py

import openai
import string
from worker import config

# Индекс для круговой смены ключей
_key_index = 0

def get_next_api_key() -> str | None:
    """
    Возвращает следующий API-ключ из списка и устанавливает его в openai.api_key.
    """
    global _key_index
    keys = config.OPENAI_API_KEYS
    if not keys:
        return None
    key = keys[_key_index]
    _key_index = (_key_index + 1) % len(keys)
    openai.api_key = key
    return key

async def ask_gpt(
    messages: list[dict],
    model: str = "gpt-3.5-turbo"
) -> str:
    """
    Отправляет список сообщений в OpenAI ChatCompletion и возвращает ответ.
    messages: [{"role":"user"|"system"|"assistant","content": "..."}]
    """
    # Подменяем ключ, если больше одного
    get_next_api_key()

    try:
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        # В случае ошибки возвращаем текст с префиксом "Ошибка GPT:"
        return f"Ошибка GPT: {e}"
