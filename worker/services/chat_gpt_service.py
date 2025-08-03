import os
import logging
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    logger = logging.getLogger(__name__)
    logger.error("❌ Missing OPENAI_API_KEY environment variable")
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

logger = logging.getLogger(__name__)
logger.info(f"🔧 OpenAI API Key loaded: {OPENAI_KEY[:10]}...")

client = OpenAI(api_key=OPENAI_KEY)


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
        
        response = client.chat.completions.create(
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
    
    logger.info(f"🔧 Обрабатываем задачу chat_gpt: task_id={task_id}, message_length={len(message)}")
    
    if not task_id:
        logger.error("❌ Отсутствует task_id в задаче chat_gpt")
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not message:
        logger.error("❌ Нет сообщения для обработки в задаче chat_gpt")
        return {"type": "error", "message": "Нет сообщения для обработки."}
    
    try:
        logger.info(f"🔧 Отправляем запрос к GPT: task_id={task_id}")
        
        # Получаем ответ от GPT
        response = await chat_with_gpt(message, context)
        
        logger.info(f"✅ Получен ответ от GPT: task_id={task_id}, response_length={len(response)}")
        
        return {
            "type": "chat_gpt",
            "task_id": task_id,
            "user_message": message,
            "context": context,
            "gpt_response": response
        }
        
    except Exception as e:
        logger.exception(f"❌ Ошибка в handle_chat_gpt для task_id={task_id}: {e}")
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при обработке чата: {str(e)}"
        } 