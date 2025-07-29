#!/usr/bin/env python3
import asyncio
import logging
import json

import aio_pika
# Добавляем импорты для HTTP запросов
import aiohttp
import base64
from io import BytesIO

from worker import config, db, redis_cache
from worker.consumers import task_consumer

# Удаляем неиспользуемую глобальную переменную publish_exchange
# publish_exchange: aio_pika.Exchange | None = None

async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            task_data = json.loads(message.body)
        except json.JSONDecodeError as e:
            logging.error(f"🔴 Failed to decode task message: {e}")
            return

        task_type  = task_data.get("type")
        user_id    = task_data.get("user_id")
        student_id = task_data.get("student_id")
        logging.info(f"▶ Получена задача: type={task_type}, user={user_id}, student={student_id}")

        # Выполняем задачу через соответствующий обработчик
        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Задача type={task_type} успешно обработана.")
        except Exception as e:
            logging.exception(f"🔴 Ошибка при обработке задачи type={task_type}")
            return

        if not result:
            logging.warning("⚠️ Обработчик задачи вернул None — результат не будет отправлен")
            return

        # Получаем необходимые данные из результата
        user_id = result.get("user_id")
        result_type = result.get("type")
        if not user_id or not result_type:
            logging.warning("⚠️ Результат не содержит user_id или type, отправка в Telegram пропущена")
            return

        # Отправляем результат напрямую в Telegram
        try:
            async with aiohttp.ClientSession() as session:
                # Отправка текстового сообщения в зависимости от типа результата
                if result_type == "chat":
                    # Ответ от ChatGPT (обычный чат)
                    text = result.get("answer", "(нет ответа)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": text,
                            "parse_mode": "HTML"
                        }
                    )
                elif result_type == "plan":
                    # Сгенерированный учебный план
                    plan_text = result.get("plan_text", "(пусто)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": f"📄 План:\n{plan_text}",
                            "parse_mode": "HTML"
                        }
                    )
                elif result_type == "tasks":
                    file_b64 = result.get("file")
                    if file_b64:
                        file_bytes = base64.b64decode(file_b64)
                        file_obj = BytesIO(file_bytes)
                        file_obj.name = "Задания.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id", str(user_id))
                        form.add_field("caption", "📎 Ваши задания в PDF")
                        form.add_field("document", file_obj, filename=file_obj.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )
                    else:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text": "⚠️ Ошибка: не удалось сгенерировать PDF с заданиями"
                            }
                        )

                elif result_type == "check":
                    # Результаты проверки домашнего задания
                    report_text = result.get("report_text", "(нет отчёта)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": f"✔️ Результаты проверки:\n{report_text}",
                            "parse_mode": "HTML"
                        }
                    )
                    # Отправляем PDF отчёт, если он есть
                    file_b64 = result.get("file")
                    if file_b64:
                        file_bytes = base64.b64decode(file_b64)
                        file_obj = BytesIO(file_bytes)
                        file_obj.name = "Homework_Report.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id", str(user_id))
                        form.add_field("caption", "📎 Отчёт в PDF")
                        form.add_field("document", file_obj, filename=file_obj.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )
                elif result_type == "error":
                    # Сообщение об ошибке
                    error_msg = result.get("message", "Неизвестная ошибка")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": f"⚠️ Ошибка: {error_msg}"
                        }
                    )
                elif result_type == "ocr":
                    text = result.get("text", "").strip()
                    if not text:
                        # если OCR вернул пустоту, уведомляем об ошибке
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={"chat_id": user_id, "text": "❌ Не удалось распознать текст на изображении."}
                        )
                    else:
                        # 1) Публикуем новый таск generate_tasks с распознанным текстом
                        new_task = {
                            "type": "generate_tasks",
                            "user_id": user_id,
                            "student_id": result.get("student_id"),
                            "prompt": text
                        }
                        await message.channel.default_exchange.publish(
                            aio_pika.Message(body=json.dumps(new_task).encode("utf-8")),
                            routing_key=config.TASK_QUEUE
                        )
                        # 2) Уведомляем пользователя, что началась генерация
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text": "🕔 Генерируются задания по распознанному тексту, ожидайте..."
                            }
                        )
                else:
                    logging.warning(f"❓ Неизвестный тип результата: {result_type}")
            logging.info(f"📨 Результат отправлен напрямую пользователю {user_id} (type={result_type})")
        except Exception as e:
            logging.exception(f"🔴 Ошибка при отправке сообщения в Telegram: {e}")
            # Здесь мы перехватываем исключения, чтобы падение Telegram API не остановило воркер
            # Можно добавить повторную попытку или сохранение неотправленного результата, если нужно

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s | %(message)s"
    )

    # 1) Инициализация подключения к БД
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    # 2) Инициализация подключения к Redis (кеш), если используется
    await redis_cache.init_redis_pool(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_DB)

    # 3) Подключение к RabbitMQ (для получения задач)
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    logging.info("✔️ Подключение к RabbitMQ (задачи) успешно установлено")

    # 4) Объявляем очередь задач (обмен default, очередь task_queue)
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    logging.info(f"🕸 Объявлена очередь задач: {config.TASK_QUEUE}")

    # (Очередь результатов можно не объявлять, так как мы отправляем данные напрямую)

    # 5) Подписка на очередь задач
    task_queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await channel.set_qos(prefetch_count=1)
    await task_queue.consume(handle_message)
    logging.info(f"✅ Подписка на очередь '{config.TASK_QUEUE}' выполнена. Ожидаю задачи...")

    # 6) Бесконечный цикл, чтобы процесс не завершался
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
