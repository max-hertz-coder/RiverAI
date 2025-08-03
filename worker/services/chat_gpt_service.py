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


async def chat_with_gpt(message: str) -> str:
    """
    Обычный чат с GPT.
    Принимает сообщение пользователя.
    """
    try:
        messages = [{"role": "user", "content": message}]
        
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
    
    logger.info(f"🔧 Обрабатываем chat_gpt: task_id={task_id}, message_length={len(message)}")
    
    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not message:
        return {"type": "error", "message": "Нет сообщения для обработки."}
    
    try:
        # Получаем контекст из Redis
        from common.redis_utils import get_context_by_task_id
        context = await get_context_by_task_id(task_id)
        if not context:
            return {"type": "error", "message": "Контекст задачи не найден."}

        user_id = context.get("user_id")
        student_id = context.get("student_id")
        
        # Получаем историю диалога
        from common.redis_utils import get_conversation, save_conversation
        history_json = await get_conversation(user_id, student_id)
        
        if history_json:
            import json
            try:
                messages = json.loads(history_json)
                logger.info(f"🔧 Найдена история диалога: {len(messages)} сообщений")
            except json.JSONDecodeError as e:
                logger.error(f"🔴 Ошибка декодирования истории диалога: {e}")
                messages = []
        else:
            messages = []
            logger.info(f"🔧 История диалога пуста, начинаем новый диалог")

        # Добавляем новое сообщение
        messages.append({"role": "user", "content": message})
        
        # Получаем ответ от GPT
        logger.info(f"🔧 Отправляем запрос к GPT...")
        response = await chat_with_gpt(message)
        logger.info(f"🔧 Получен ответ от GPT: {len(response)} символов")
        
        # Добавляем ответ в историю
        messages.append({"role": "assistant", "content": response})
        
        # Сохраняем обновленную историю
        try:
            await save_conversation(user_id, student_id, json.dumps(messages, ensure_ascii=False))
            logger.info(f"🔧 История диалога сохранена")
        except Exception as e:
            logger.error(f"🔴 Ошибка сохранения истории диалога: {e}")
        
        return {
            "type": "chat_gpt",
            "gpt_response": response.strip()
        }
        
    except Exception as e:
        logger.exception("Ошибка в handle_chat_gpt: %s", e)
        return {
            "type": "error",
            "message": f"Ошибка при обработке чата: {str(e)}"
        } 