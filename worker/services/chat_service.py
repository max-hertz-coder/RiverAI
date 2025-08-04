
# 📁 Новый файл: worker/services/

import logging
import json
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from common.redis_utils import get_context_by_task_id, get_conversation, save_conversation

load_dotenv()
logger = logging.getLogger(__name__)

# Инициализация OpenAI
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY не найден")

client = AsyncOpenAI(api_key=OPENAI_KEY)

async def chat_with_gpt_simple(message: str, history: list = None) -> str:
    """
    Простая функция для чата с GPT
    """
    try:
        # Формируем сообщения
        messages = []
        
        # Добавляем историю
        if history:
            messages.extend(history)
        
        # Добавляем текущее сообщение
        messages.append({"role": "user", "content": message})
        
        logger.info(f"Отправляем в GPT: {len(messages)} сообщений")
        
        # Вызываем GPT
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        answer = response.choices[0].message.content.strip()
        logger.info(f"Получен ответ от GPT: {len(answer)} символов")
        
        return answer
        
    except Exception as e:
        logger.exception(f"Ошибка в GPT: {e}")
        return f"Ошибка при обращении к GPT: {str(e)}"

async def handle_chat(task: dict) -> dict:
    """
    Обработчик чата с GPT
    """
    logger.info("=== НАЧАЛО ОБРАБОТКИ ЧАТА ===")
    
    try:
        # Получаем данные
        task_id = task.get("task_id")
        message = task.get("message", "").strip()
        task_type = task.get("type")
        
        logger.info(f"task_id={task_id}, type={task_type}, message='{message[:30]}...'")
        
        # Проверки
        if not task_id:
            logger.error("Нет task_id")
            return {"type": "error", "message": "Нет task_id"}
        
        if not message and task_type != "end_chat":
            logger.error("Пустое сообщение")
            return {"type": "error", "message": "Пустое сообщение"}
        
        # Получаем контекст
        logger.info("Получаем контекст из Redis")
        context = await get_context_by_task_id(task_id)
        if not context:
            logger.error(f"Контекст не найден для {task_id}")
            return {"type": "error", "message": "Контекст не найден"}
        
        user_id = context.get("user_id")
        student_id = context.get("student_id")
        
        logger.info(f"user_id={user_id}, student_id={student_id}")
        
        if not user_id or not student_id:
            logger.error("Нет user_id или student_id")
            return {"type": "error", "message": "Нет user_id или student_id"}
        
        # Очистка чата
        if task_type == "end_chat":
            logger.info("Очищаем историю")
            from common.redis_utils import clear_conversation
            await clear_conversation(user_id, student_id)
            return {"type": "chat", "answer": "🗑️ Диалог очищен"}
        
        # Получаем историю
        logger.info("Получаем историю диалога")
        history_json = await get_conversation(user_id, student_id)
        history = []
        
        if history_json:
            try:
                history = json.loads(history_json)
                logger.info(f"Найдена история: {len(history)} сообщений")
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка декодирования истории: {e}")
                history = []
        else:
            logger.info("История пуста")
        
        # Получаем ответ от GPT
        logger.info("Вызываем GPT")
        response = await chat_with_gpt_simple(message, history)
        
        # Проверяем на ошибку
        if response.startswith("Ошибка"):
            logger.error(f"GPT вернул ошибку: {response}")
            return {"type": "error", "message": response}
        
        # Обновляем историю
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})
        
        # Сохраняем историю
        try:
            await save_conversation(user_id, student_id, json.dumps(history, ensure_ascii=False))
            logger.info("История сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")
        
        # Возвращаем результат
        result = {"type": "chat", "answer": response}
        logger.info("=== УСПЕШНО ЗАВЕРШЕНО ===")
        return result
        
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {"type": "error", "message": f"Ошибка: {str(e)}"}