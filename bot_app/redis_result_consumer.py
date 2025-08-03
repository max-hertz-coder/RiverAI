import json
import logging
import asyncio
from typing import Dict, Any
from aiogram import Bot
from aiogram.types import FSInputFile
import tempfile
import os

from bot_app.config import BOT_TOKEN
from common.redis_utils import get_context_by_task_id, cleanup_task_context

bot = Bot(token=BOT_TOKEN)
logger = logging.getLogger(__name__)

async def process_result(result: Dict[str, Any]):
    """
    Обрабатывает результат из Redis и отправляет ответ пользователю.
    """
    task_id = result.get("task_id")
    result_type = result.get("type")
    
    if not task_id:
        logger.error("❌ Результат без task_id")
        return
    
    # Получаем контекст задачи
    context = await get_context_by_task_id(task_id)
    if not context:
        logger.error(f"❌ Не найден контекст для task_id={task_id}")
        return
    
    user_id = context.get("user_id")
    if not user_id:
        logger.error(f"❌ Не найден user_id в контексте для task_id={task_id}")
        return
    
    try:
        if result_type == "generate_tasks":
            await handle_generate_tasks_result(result, user_id)
        elif result_type == "check_homework":
            await handle_check_homework_result(result, user_id)
        elif result_type == "chat_gpt":
            await handle_chat_gpt_result(result, user_id)
        elif result_type == "ocr_and_generate":
            await handle_ocr_and_generate_result(result, user_id)
        elif result_type == "error":
            await handle_error_result(result, user_id)
        else:
            logger.warning(f"❓ Неизвестный тип результата: {result_type}")
            
    except Exception as e:
        logger.exception(f"❌ Ошибка обработки результата {result_type}: {e}")
        await bot.send_message(user_id, f"❌ Ошибка обработки результата: {str(e)}")
    finally:
        # Очищаем контекст задачи
        await cleanup_task_context(task_id)

async def handle_generate_tasks_result(result: Dict[str, Any], user_id: int):
    """Обрабатывает результат генерации заданий"""
    raw_tasks = result.get("raw_tasks", "")
    
    if not raw_tasks:
        await bot.send_message(user_id, "❌ Не удалось сгенерировать задания.")
        return
    
    # Отправляем текстовый результат
    await bot.send_message(
        user_id, 
        f"📝 **Сгенерированные задания:**\n\n{raw_tasks}",
        parse_mode="Markdown"
    )

async def handle_check_homework_result(result: Dict[str, Any], user_id: int):
    """Обрабатывает результат проверки домашнего задания"""
    check_result = result.get("check_result", "")
    
    if not check_result:
        await bot.send_message(user_id, "❌ Не удалось проверить домашнее задание.")
        return
    
    # Отправляем текстовый результат
    await bot.send_message(
        user_id, 
        f"📄 **Результат проверки ДЗ:**\n\n{check_result}",
        parse_mode="Markdown"
    )

async def handle_chat_gpt_result(result: Dict[str, Any], user_id: int):
    """Обрабатывает результат чата с GPT"""
    gpt_response = result.get("gpt_response", "")
    
    if not gpt_response:
        await bot.send_message(user_id, "❌ Не удалось получить ответ от GPT.")
        return
    
    # Отправляем ответ GPT
    await bot.send_message(
        user_id, 
        f"💬 **Ответ GPT:**\n\n{gpt_response}",
        parse_mode="Markdown"
    )

async def handle_ocr_and_generate_result(result: Dict[str, Any], user_id: int):
    """Обрабатывает результат OCR + генерации"""
    ocr_text = result.get("ocr_text", "")
    raw_tasks = result.get("raw_tasks", "")
    
    if not ocr_text:
        await bot.send_message(user_id, "❌ Не удалось распознать текст из изображения.")
        return
    
    if not raw_tasks:
        await bot.send_message(user_id, "❌ Не удалось сгенерировать задания.")
        return
    
    # Отправляем распознанный текст
    await bot.send_message(
        user_id, 
        f"📷 **Распознанный текст:**\n\n{ocr_text}",
        parse_mode="Markdown"
    )
    
    # Отправляем сгенерированные задания
    await bot.send_message(
        user_id, 
        f"📝 **Сгенерированные задания:**\n\n{raw_tasks}",
        parse_mode="Markdown"
    )

async def handle_error_result(result: Dict[str, Any], user_id: int):
    """Обрабатывает ошибку"""
    error_message = result.get("message", "Неизвестная ошибка")
    await bot.send_message(user_id, f"❌ {error_message}")


async def consume_redis_results(bot: Bot):
    """Проверяет Redis на наличие результатов каждые 2 секунды"""
    from common.redis_utils import _get_client

    logging.info("🔧 Запускаем проверку результатов в Redis...")

    while True:
        try:
            client = _get_client()
            result_keys = await client.keys("result:*")

            for key in result_keys:
                try:
                    result_json = await client.get(key)
                    if result_json:
                        result_data = json.loads(result_json)
                        await process_result(result_data)
                        await client.delete(key)
                        logging.info(f"✅ Обработан результат из Redis: {key}")
                except Exception as e:
                    logging.error(f"🔴 Ошибка обработки результата из Redis {key}: {e}")

            await asyncio.sleep(2)

        except Exception as e:
            logging.error(f"🔴 Ошибка в consume_redis_results: {e}")
            await asyncio.sleep(5)
