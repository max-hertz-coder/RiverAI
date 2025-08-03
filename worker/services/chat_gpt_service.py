import os
import logging
from typing import Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = AsyncOpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)


async def chat_with_gpt(message: str, context: str = "") -> str:
    """
    Обычный чат с GPT.
    Принимает сообщение пользователя и опциональный контекст.
    """
    try:
        messages = []
        
        # Добавляем контекст, если есть
        if context:
            messages.append({
                "role": "system", 
                "content": f"Контекст: {context}\n\nОтвечайте на русском языке."
            })
        
        # Добавляем сообщение пользователя
        messages.append({
            "role": "user",
            "content": message
        })
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.exception("Ошибка в чате с GPT: %s", e)
        return f"❌ Ошибка при общении с GPT: {str(e)}"


async def handle_chat_gpt(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик задачи чата с GPT.
    Принимает task с полями: task_id, message (сообщение пользователя), context (опционально)
    Возвращает ответ от GPT.
    """
    task_id = task.get("task_id")
    message = task.get("message", "").strip()
    context = task.get("context", "").strip()
    
    logger.info(f"🔧 Обрабатываем chat_gpt: task_id={task_id}, message_length={len(message)}")
    
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not message:
        return {"type": "error", "message": "Нет сообщения для обработки."}
    
    try:
        # Получаем ответ от GPT
        logger.info(f"🔧 Отправляем запрос к GPT...")
        response = await chat_with_gpt(message, context)
        logger.info(f"🔧 Получен ответ от GPT: {len(response)} символов")
        
        return {
            "type": "chat_gpt",
            "task_id": task_id,
            "user_message": message,
            "context": context,
            "gpt_response": response
        }
        
    except Exception as e:
        logger.exception("Ошибка в handle_chat_gpt: %s", e)
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при обработке чата: {str(e)}"
        } 