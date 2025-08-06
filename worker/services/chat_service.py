# ===== НОВАЯ ВЕРСИЯ CHAT_SERVICE.PY - 2025-08-04 =====
import os
import json
import logging
from openai import AsyncOpenAI
from common.redis_utils import get_context_by_task_id, get_conversation, save_conversation
from worker.services.gpt_service import chat_with_gpt
from worker import db

logger = logging.getLogger(__name__)

# ТЕСТОВАЯ ФУНКЦИЯ - ДОЛЖНА БЫТЬ ВИДНА В ЛОГАХ
def test_function():
    logger.info("🔧 ТЕСТОВАЯ ФУНКЦИЯ ВЫЗВАНА - chat_service.py загружен")

# Вызываем тестовую функцию при загрузке модуля
test_function()

# Инициализация OpenAI
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY не найден")

client = AsyncOpenAI(api_key=OPENAI_KEY)

async def chat_with_gpt_simple(message: str, history: list = None) -> str:
    """
    Простая функция для чата с GPT (для обратной совместимости)
    """
    try:
        logger.info(f"🔧 chat_with_gpt_simple: начало, message_length={len(message)}")
        
        # Формируем сообщения
        messages = []
        
        # Добавляем историю
        if history:
            messages.extend(history)
            logger.info(f"🔧 chat_with_gpt_simple: добавлена история, {len(history)} сообщений")
        
        # Добавляем текущее сообщение
        messages.append({"role": "user", "content": message})
        
        logger.info(f"🔧 chat_with_gpt_simple: отправляем в GPT, всего сообщений: {len(messages)}")
        
        # Вызываем GPT с подсчетом токенов
        logger.info(f"🔧 chat_with_gpt_simple: создаем запрос к OpenAI...")
        response = await chat_with_gpt(messages, temperature=0.7, max_tokens=1000)
        
        logger.info(f"🔧 chat_with_gpt_simple: получен ответ от OpenAI")
        answer = response["text"]
        logger.info(f"🔧 chat_with_gpt_simple: ответ GPT, {len(answer)} символов")
        
        return answer
        
    except Exception as e:
        logger.exception(f"🔴 chat_with_gpt_simple: ошибка: {e}")
        logger.error(f"🔴 Тип ошибки: {type(e).__name__}")
        return f"Ошибка при обращении к GPT: {str(e)}"

async def handle_chat(task: dict) -> dict:
    """
    Обработчик чата с GPT - НОВАЯ ВЕРСИЯ 2025-08-04 с подсчетом токенов
    """
    logger.info("=== НАЧАЛО ОБРАБОТКИ ЧАТА - НОВАЯ ВЕРСИЯ ===")
    
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
        
        # Получаем ответ от GPT с подсчетом токенов
        logger.info("🔧 handle_chat: вызываем GPT")
        try:
            # Формируем сообщения для GPT
            messages = []
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": message})
            
            response = await chat_with_gpt(messages, temperature=0.7, max_tokens=1000)
            logger.info(f"🔧 handle_chat: GPT вернул ответ, длина: {len(response['text'])}")
            
            # Сохраняем статистику токенов в БД
            try:
                await db.increment_token_usage(user_id, response["prompt_tokens"], response["completion_tokens"])
                await db.increment_student_token_usage(student_id, response["prompt_tokens"], response["completion_tokens"])
                logger.info(f"🔧 handle_chat: статистика токенов сохранена в БД")
            except Exception as e:
                logger.error(f"🔴 handle_chat: ошибка сохранения статистики токенов: {e}")
            
        except Exception as e:
            logger.exception(f"🔴 handle_chat: ошибка при вызове GPT: {e}")
            return {"type": "error", "message": f"Ошибка при вызове GPT: {str(e)}"}
        
        # Проверяем на ошибку
        if response["text"].startswith("Ошибка"):
            logger.error(f"🔴 handle_chat: GPT вернул ошибку: {response['text']}")
            return {"type": "error", "message": response["text"]}
        
        logger.info(f"🔧 handle_chat: успешно получили ответ от GPT")
        
        # Обновляем историю
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response["text"]})
        logger.info(f"🔧 handle_chat: обновили историю, теперь {len(history)} сообщений")
        
        # Сохраняем историю
        try:
            await save_conversation(user_id, student_id, json.dumps(history, ensure_ascii=False))
            logger.info("🔧 handle_chat: история сохранена в Redis")
        except Exception as e:
            logger.error(f"🔴 handle_chat: ошибка сохранения истории: {e}")
        
        # Возвращаем результат
        result = {"type": "chat", "answer": response["text"]}
        logger.info("🔧 handle_chat: УСПЕШНО ЗАВЕРШЕНО - НОВАЯ ВЕРСИЯ")
        return result
        
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {"type": "error", "message": f"Ошибка: {str(e)}"}