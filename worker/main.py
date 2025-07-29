#!/usr/bin/env python3
import asyncio
import logging
import json
import base64
from io import BytesIO

import aio_pika
import aiohttp

from worker import config, db, redis_cache
from worker.consumers import task_consumer

async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        # 1) Распаковываем задачу
        try:
            task_data = json.loads(message.body)
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        task_type  = task_data.get("type")
        user_id    = task_data.get("user_id")
        student_id = task_data.get("student_id")
        logging.info(f"▶ Received task: type={task_type}, user_id={user_id}, student_id={student_id}")

        # 2) Обрабатываем задачу
        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Task processed: type={task_type}")
        except Exception:
            logging.exception(f"🔴 Error processing task type={task_type}")
            return

        if not result:
            logging.warning("⚠️ Handler returned None — skipping")
            return

        user_id     = result.get("user_id")
        result_type = result.get("type")
        if not user_id or not result_type:
            logging.warning("⚠️ Invalid result (missing user_id or type) — skipping")
            return

        # 3) Отправляем результат в Telegram через HTTP
        try:
            async with aiohttp.ClientSession() as session:

                # === Chat response ===
                if result_type == "chat":
                    text = result.get("answer", "(нет ответа)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user_id, "text": text, "parse_mode": "HTML"}
                    )

                # === Study plan ===
                elif result_type == "plan":
                    plan_text = result.get("plan_text", "(пусто)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": f"📄 План:\n{plan_text}",
                            "parse_mode": "HTML"
                        }
                    )

                # === Generated tasks ===
                elif result_type == "tasks":
                    prompt = result.get("prompt", "").strip()
                    raw    = result.get("raw_tasks_text", "").strip()

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
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id":      user_id,
                            "text":         text,
                            "parse_mode":   "HTML",
                            "reply_markup": kb
                        }
                    )

                    # Отправляем PDF
                    file_b64 = result.get("file")
                    if file_b64:
                        pdf_bytes = base64.b64decode(file_b64)
                        buf = BytesIO(pdf_bytes)
                        buf.name = "Задания.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id",  str(user_id))
                        form.add_field("caption",   "📎 Ваши задания в PDF")
                        form.add_field("document",  buf, filename=buf.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )
                    else:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text":    "⚠️ Не удалось сгенерировать PDF с заданиями"
                            }
                        )

                # === Homework check ===
                elif result_type == "check":
                    report = result.get("report_text", "(нет отчёта)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id":    user_id,
                            "text":       f"✔️ Результаты проверки:\n{report}",
                            "parse_mode": "HTML"
                        }
                    )
                    file_b64 = result.get("file")
                    if file_b64:
                        pdf_bytes = base64.b64decode(file_b64)
                        buf = BytesIO(pdf_bytes)
                        buf.name = "Homework_Report.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id",  str(user_id))
                        form.add_field("caption",   "📎 Отчёт в PDF")
                        form.add_field("document",  buf, filename=buf.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )

                # === Error ===
                elif result_type == "error":
                    error_msg = result.get("message", "Неизвестная ошибка")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text":    f"⚠️ Ошибка: {error_msg}"
                        }
                    )

                # === OCR-only (without generate) ===
                elif result_type == "ocr":
                    user_prompt = result.get("prompt", "").strip()
                    ocr_text    = result.get("text", "").strip()

                    if not ocr_text:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text":    "❌ Не удалось распознать текст на изображении."
                            }
                        )
                    else:
                        # Формируем финальный промт и сразу републикуем generate_tasks
                        final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text
                        # Показываем финальный промт
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text":    f"🔄 Финальный запрос для генерации:\n{final_prompt}"
                            }
                        )
                        # Републикуем задачу
                        new_task = {
                            "type":         "generate_tasks",
                            "user_id":      user_id,
                            "student_id":   student_id,
                            "prompt":       final_prompt
                        }
                        # Отправляем в очередь
                        conn = await aio_pika.connect_robust(
                            host=config.RABBITMQ_HOST,
                            port=config.RABBITMQ_PORT,
                            login=config.RABBITMQ_USER,
                            password=config.RABBITMQ_PASS,
                        )
                        ch = await conn.channel()
                        await ch.default_exchange.publish(
                            aio_pika.Message(body=json.dumps(new_task).encode()),
                            routing_key=config.TASK_QUEUE
                        )
                        await conn.close()
                        # Уведомляем пользователя
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text":    "🕔 Генерируются задания, ожидайте..."
                            }
                        )

                else:
                    logging.warning(f"❓ Unknown result type: {result_type}")

            logging.info(f"📨 Result sent to user={user_id}, type={result_type}")

        except Exception:
            logging.exception("🔴 Error sending message via Telegram")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")

    # 1) Инициализация PostgreSQL
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    # 2) Инициализация Redis
    await redis_cache.init_redis_pool(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_DB)

    # 3) Подключение к RabbitMQ и подписка
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await queue.consume(handle_message)
    logging.info(f"✅ Subscribed to '{config.TASK_QUEUE}', awaiting tasks...")

    # 4) Не завершаемся
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())