### ✅ ОБНОВЛЕННЫЙ ФАЙЛ: bot_app/rabbit.py

import json
import logging
from io import BytesIO
import base64
from aiogram import Bot
from common.redis_utils import get_context_by_task_id, cleanup_task_context
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb
)

pending_tasks: dict[tuple[int, int], str] = {}

async def process_result(message, bot: Bot):
    async with message.process():
        try:
            data = json.loads(message.body)
            logging.info(f"📥 Результат из очереди: {data}")
        except Exception as e:
            logging.error(f"❌ Не удалось разобрать JSON: {e}")
            return

        task_id = data.get("task_id")
        if not task_id:
            logging.warning("⚠️ В результате нет task_id")
            return

        context = await get_context_by_task_id(task_id)
        if not context:
            logging.warning(f"⚠️ Контекст не найден для task_id={task_id}")
            return

        user_id = context.get("user_id")
        student_id = context.get("student_id")
        result_type = data.get("type")

        if not user_id or not result_type:
            logging.warning("⚠️ В результате нет user_id или type")
            return

        try:
            # === Chat response ===
            if result_type == "chat":
                text = data.get("answer", "(нет ответа)")
                await bot.send_message(
                    user_id, 
                    text, 
                    reply_markup=chat_gpt_back_kb(student_id)
                )

            # === Study plan ===
            elif result_type == "plan":
                plan_text = data.get("plan_text", "(пусто)")
                await bot.send_message(
                    user_id,
                    f"📄 План:\n{plan_text}",
                    reply_markup=result_plan_kb(student_id)
                )

            # === Generated tasks ===
            elif result_type == "tasks":
                prompt = data.get("prompt", "").strip()
                raw = data.get("tasks_text", "").strip()

                # Собираем единое сообщение
                parts = []
                if prompt:
                    parts.append(f"🔄 Финальный запрос для генерации:\n{prompt}")
                if raw:
                    parts.append(f"📝 Задания:\n\n{raw}")
                parts.append("❓ Всё ли устраивает?")
                text = "\n\n".join(parts)

                kb = {
                    "inline_keyboard": [[
                        {"text": "✅ Всё норм",    "callback_data": "tasks_ok"},
                        {"text": "✏️ Переделать", "callback_data": f"refine_tasks:{student_id}"}
                    ]]
                }

                # Отправляем текст с кнопками
                await bot.send_message(
                    user_id,
                    text,
                    reply_markup=kb
                )

                # Отправляем PDF
                file_tasks_b64 = data.get("file_tasks")
                file_solutions_b64 = data.get("file_solutions")

                if file_tasks_b64:
                    file_bytes = base64.b64decode(file_tasks_b64)
                    file_obj = BytesIO(file_bytes)
                    file_obj.name = "Tasks.pdf"
                    await bot.send_document(user_id, file_obj, caption="📎 PDF: Задания")

                if file_solutions_b64:
                    file_bytes = base64.b64decode(file_solutions_b64)
                    file_obj = BytesIO(file_bytes)
                    file_obj.name = "Solutions.pdf"
                    await bot.send_document(user_id, file_obj, caption="📎 PDF: Решения")

            # === Homework check ===
            elif result_type == "check":
                report = data.get("report_text", "(нет отчёта)")
                await bot.send_message(
                    user_id,
                    f"✔️ Результаты проверки:\n{report}",
                    reply_markup=result_check_kb(student_id)
                )
                
                file_b64 = data.get("file")
                if file_b64:
                    pdf_bytes = base64.b64decode(file_b64)
                    buf = BytesIO(pdf_bytes)
                    buf.name = "Homework_Report.pdf"
                    await bot.send_document(user_id, buf, caption="📎 Отчёт в PDF")

            # === Error ===
            elif result_type == "error":
                error_msg = data.get("message", "Неизвестная ошибка")
                await bot.send_message(
                    user_id,
                    f"⚠️ Ошибка: {error_msg}"
                )

            # === OCR-only (without generate) ===
            elif result_type == "ocr":
                user_prompt = data.get("prompt", "").strip()
                ocr_text = data.get("text", "").strip()

                if not ocr_text:
                    await bot.send_message(
                        user_id,
                        "❌ Не удалось распознать текст на изображении."
                    )
                else:
                    # Формируем финальный промт и сразу републикуем generate_tasks
                    final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text
                    
                    # Показываем финальный промт
                    await bot.send_message(
                        user_id,
                        f"🔄 Финальный запрос для генерации:\n{final_prompt}"
                    )
                    
                    # Создаем новую задачу для генерации
                    from bot_app.utils.task_utils import create_task_with_context
                    new_task = {
                        "type": "generate_tasks",
                        "user_id": user_id,
                        "student_id": student_id,
                        "prompt": final_prompt
                    }
                    
                    # Отправляем в очередь
                    from bot_app import config
                    import aio_pika
                    
                    task_with_context = await create_task_with_context(new_task)
                    conn = await aio_pika.connect_robust(
                        host=config.RABBITMQ_HOST,
                        port=config.RABBITMQ_PORT,
                        login=config.RABBITMQ_USER,
                        password=config.RABBITMQ_PASS,
                    )
                    ch = await conn.channel()
                    await ch.default_exchange.publish(
                        aio_pika.Message(body=json.dumps(task_with_context).encode()),
                        routing_key=config.TASK_QUEUE
                    )
                    await conn.close()
                    
                    # Уведомляем пользователя
                    await bot.send_message(
                        user_id,
                        "🕔 Генерируются задания, ожидайте..."
                    )

            else:
                logging.warning(f"❓ Unknown result type: {result_type}")

            logging.info(f"✅ Отправлено пользователю {user_id} по task_id={task_id}")

        except Exception as e:
            logging.exception(f"🔴 Ошибка отправки результата пользователю {user_id}: {e}")

        finally:
            # Очищаем контекст задачи
            await cleanup_task_context(task_id)
