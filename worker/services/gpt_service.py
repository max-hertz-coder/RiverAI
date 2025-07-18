# worker/services/gpt_service.py

import openai
from bot_app import config

# По очереди перебираем ключи из config.OPENAI_API_KEYS
_key_index = 0
def _get_next_api_key():
    global _key_index
    keys = config.OPENAI_API_KEYS
    if not keys:
        return None
    key = keys[_key_index]
    _key_index = (_key_index + 1) % len(keys)
    return key

async def chat_with_gpt(
    prompt: str,
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.7
) -> str:
    """
    Отправляет одиночное сообщение пользователю в ChatCompletion API.
    Возвращает текст ответа или сообщение об ошибке.
    """
    api_key = _get_next_api_key()
    if api_key:
        openai.api_key = api_key

    try:
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        # Возвращаем текст ошибки, чтобы воркер мог её залогировать
        return f"GPT error: {e}"
