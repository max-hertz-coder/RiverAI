import logging
import random
import asyncio
from openai import AsyncOpenAI
from worker import config

logger = logging.getLogger(__name__)

# Инициализация OpenAI клиента (рандомный ключ)
def _get_openai_client():
    key = random.choice(config.OPENAI_API_KEYS)
    logger.info(f"🔧 Используем OpenAI ключ: {key[:10]}...")
    return AsyncOpenAI(api_key=key)

async def chat_with_gpt(messages: list[dict], temperature=0.7, max_tokens=1000) -> str:
    """
    Универсальный вызов GPT (chat-based).
    """
    logger.info(f"🔧 Начинаем вызов GPT API:")
    logger.info(f"  Количество сообщений: {len(messages)}")
    logger.info(f"  Последнее сообщение: {messages[-1]['content'][:100]}...")
    
    client = _get_openai_client()
    try:
        logger.info(f"🔧 Отправляем запрос к GPT API...")
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        logger.info(f"🔧 Получен ответ от GPT API")
        result = response.choices[0].message.content.strip()
        logger.info(f"🔧 Ответ GPT: {len(result)} символов")
        return result
    except Exception as e:
        logger.error(f"🔴 Ошибка с gpt-4o: {e}")
        # Попробуем с gpt-3.5-turbo как fallback
        try:
            logger.info(f"🔧 Пробуем с gpt-3.5-turbo...")
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            logger.info(f"🔧 Получен ответ от GPT-3.5 API")
            result = response.choices[0].message.content.strip()
            logger.info(f"🔧 Ответ GPT-3.5: {len(result)} символов")
            return result
        except Exception as e2:
            logger.exception(f"🔴 Ошибка в chat_with_gpt (оба варианта): {e2}")
            raise e2