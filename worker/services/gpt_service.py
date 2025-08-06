import logging
import random
import asyncio
from openai import AsyncOpenAI
from worker import config

logger = logging.getLogger(__name__)

# Инициализация OpenAI клиента (рандомный ключ)
def _get_openai_client():
    if not config.OPENAI_API_KEYS:
        raise RuntimeError("OPENAI_API_KEYS не настроены")
    
    key = random.choice(config.OPENAI_API_KEYS)
    logger.info(f"🔧 Используем OpenAI ключ: {key[:10]}...")
    
    if not key or len(key) < 10:
        logger.error(f"🔴 Недействительный OpenAI ключ: {key[:10] if key else 'None'}...")
        raise RuntimeError("Недействительный OpenAI ключ")
    
    return AsyncOpenAI(api_key=key)

async def chat_with_gpt(messages: list[dict], temperature=0.7, max_tokens=1000) -> dict:
    """
    Универсальный вызов GPT (chat-based) с подсчетом токенов.
    Возвращает словарь с ответом и информацией о токенах.
    """
    logger.info(f"🔧 Начинаем вызов GPT API:")
    logger.info(f"  Количество сообщений: {len(messages)}")
    logger.info(f"  Последнее сообщение: {messages[-1]['content'][:100]}...")
    
    # Retry механизм
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = _get_openai_client()
            logger.info(f"🔧 Попытка {attempt + 1}/{max_retries}: отправляем запрос к GPT API...")
            
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            logger.info(f"🔧 Получен ответ от GPT API")
            result = response.choices[0].message.content.strip()
            logger.info(f"🔧 Ответ GPT: {len(result)} символов")
            
            # Подсчитываем токены
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
            
            logger.info(f"🔧 Токены: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
            
            return {
                "text": result,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
            
        except Exception as e:
            logger.error(f"🔴 Попытка {attempt + 1}/{max_retries} с gpt-4o: {e}")
            logger.error(f"🔴 Тип ошибки: {type(e).__name__}")
            
            if attempt == max_retries - 1:
                # Последняя попытка - пробуем gpt-3.5-turbo
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
                    
                    # Подсчитываем токены
                    prompt_tokens = response.usage.prompt_tokens
                    completion_tokens = response.usage.completion_tokens
                    total_tokens = response.usage.total_tokens
                    
                    logger.info(f"🔧 Токены: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
                    
                    return {
                        "text": result,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens
                    }
                except Exception as e2:
                    logger.exception(f"🔴 Ошибка в chat_with_gpt (оба варианта): {e2}")
                    logger.error(f"🔴 Тип второй ошибки: {type(e2).__name__}")
                    raise e2
            else:
                # Ждем перед следующей попыткой
                await asyncio.sleep(1)
                continue