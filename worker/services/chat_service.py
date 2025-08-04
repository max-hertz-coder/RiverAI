
# 📁 Новый файл: worker/services/

import logging
import json
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from common.redis_utils import get_context_by_task_id, get_conversation, save_conversation

load_dotenv()
logger = logging.getLogger(__name__)

# Инициализация OpenAI клиента
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    logger.error("🔴 OPENAI_API_KEY не найден в переменных окружения")
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = AsyncOpenAI(api_key=OPENAI_KEY)

async def simple_chat_with_gpt(message: str, history: list = None) -> str:
    """
    Простой чат с GPT без сложной логики
    """
    try:
        # Формируем сообщения для GPT
        messages = []
        
        # Добавляем историю если есть
        if history:
            messages.extend(history)
        
        # Добавляем текущее сообщение
        messages.append({"role": "user", "content": message})
        
        logger.info(f"🔧 Отправляем запрос к GPT: {len(messages)} сообщений")
        
        # Вызываем GPT
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        answer = response.choices[0].message.content.strip()
        logger.info(f"🔧 Получен ответ от GPT: {len(answer)} символов")
        
        return answer
        
    except Exception as e:
        logger.exception(f"🔴 Ошибка в simple_chat_with_gpt: {e}")
        return f"❌ Ошибка при обращении к GPT: {str(e)}"

async def handle_chat(task: dict) -> dict:
    """
    Простой обработчик чата с GPT
    """
    logger.info(f"🔧 handle_chat: начало")
    
    try:
        # Получаем данные из задачи
        task_id = task.get("task_id")
        message = task.get("message", "").strip()
        task_type = task.get("type")
        
        logger.info(f"🔧 handle_chat: task_id={task_id}, type={task_type}, message='{message[:50]}...'")
        
        # Проверяем обязательные поля
        if not task_id:
            logger.error("🔴 handle_chat: отсутствует task_id")
            return {"type": "error", "message": "Отсутствует task_id"}
        
        if not message and task_type != "end_chat":
            logger.error("🔴 handle_chat: сообщение пустое")
            return {"type": "error", "message": "Сообщение пустое"}
        
        # Получаем контекст из Redis
        logger.info(f"🔧 handle_chat: получаем контекст")
        context = await get_context_by_task_id(task_id)
        if not context:
            logger.error(f"🔴 handle_chat: контекст не найден для task_id={task_id}")
            return {"type": "error", "message": "Контекст задачи не найден"}
        
        user_id = context.get("user_id")
        student_id = context.get("student_id")
        
        logger.info(f"🔧 handle_chat: user_id={user_id}, student_id={student_id}")
        
        if not user_id or not student_id:
            logger.error(f"🔴 handle_chat: отсутствует user_id или student_id")
            return {"type": "error", "message": "Ошибка: отсутствует user_id или student_id"}
        
        # Обработка очистки чата
        if task_type == "end_chat":
            logger.info(f"🔧 handle_chat: очищаем историю")
            from common.redis_utils import clear_conversation
            await clear_conversation(user_id, student_id)
            return {"type": "chat", "answer": "🗑️ Диалог очищен"}
        
        # Получаем историю диалога
        logger.info(f"🔧 handle_chat: получаем историю")
        history_json = await get_conversation(user_id, student_id)
        history = []
        
        if history_json:
            try:
                history = json.loads(history_json)
                logger.info(f"🔧 handle_chat: найдена история: {len(history)} сообщений")
            except json.JSONDecodeError as e:
                logger.error(f"🔴 handle_chat: ошибка декодирования истории: {e}")
                history = []
        else:
            logger.info(f"🔧 handle_chat: история пуста")
        
        # Получаем ответ от GPT
        logger.info(f"🔧 handle_chat: вызываем GPT")
        response = await simple_chat_with_gpt(message, history)
        
        # Проверяем на ошибку
        if response.startswith("❌"):
            logger.error(f"🔴 handle_chat: GPT вернул ошибку: {response}")
            return {"type": "error", "message": response}
        
        # Обновляем историю
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})
        
        # Сохраняем историю
        try:
            await save_conversation(user_id, student_id, json.dumps(history, ensure_ascii=False))
            logger.info(f"🔧 handle_chat: история сохранена")
        except Exception as e:
            logger.error(f"🔴 handle_chat: ошибка сохранения истории: {e}")
        
        # Возвращаем результат
        result = {"type": "chat", "answer": response}
        logger.info(f"🔧 handle_chat: успешно завершено")
        return result
        
    except Exception as e:
        logger.exception(f"🔴 handle_chat: неожиданная ошибка: {e}")
        return {"type": "error", "message": f"Ошибка при обработке чата: {str(e)}"}