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

# Глобальный exchange для републикации задач
publish_exchange: aio_pika.Exchange | None = None

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

        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Задача type={task_type} успешно обработана.")
        except Exception:
            logging.exception(f"🔴 Ошибка при обработке задачи type={task_type}")
            return

        if not result:
            logging.warning("⚠️ Обработчик задачи вернул None — не отправляем")
            return

        user_id     = result.get("user_id")
        result_type = result.get("type")
        if not user_id or not result_type:
            logging.warning("⚠️ Результат без user_id/type — пропускаем")
            return

        try:
            async with aiohttp.ClientSession() as session:

                # === CHAT ===
                if result_type == "chat":
                    text = result.get("answer", "(нет ответа)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user_id, "text": text, "parse_mode": "HTML"}
                    )

                # === PLAN ===
                elif result_type == "plan":
                    plan = result.get("plan_text", "(пусто)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user_id, "text": f"📄 План:\n{plan}", "parse_mode": "HTML"}
                    )

                # === TASKS PDF ===
                elif result_type == "tasks":
                    b64 = result.get("file")
                    if b64:
                        pdf = base64.b64decode(b64)
                        buf = BytesIO(pdf); buf.name = "Задания.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id", str(user_id))
                        form.add_field("caption", "📎 Ваши задания в PDF")
                        form.add_field("document", buf, filename=buf.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )
                    else:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={"chat_id": user_id, "text": "⚠️ Не удалось сгенерировать PDF с заданиями"}
                        )

                # === HOMEWORK CHECK ===
                elif result_type == "check":
                    report = result.get("report_text", "(нет отчёта)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user_id, "text": f"✔️ Результаты проверки:\n{report}", "parse_mode": "HTML"}
                    )
                    b64 = result.get("file")
                    if b64:
                        pdf = base64.b64decode(b64)
                        buf = BytesIO(pdf); buf.name = "Homework_Report.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id", str(user_id))
                        form.add_field("caption", "📎 Отчёт в PDF")
                        form.add_field("document", buf, filename=buf.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )

                # === ERROR ===
                elif result_type == "error":
                    err = result.get("message", "Неизвестная ошибка")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user_id, "text": f"⚠️ Ошибка: {err}"}
                    )

                # === OCR → GENERATE TASKS ===
                elif result_type == "ocr":
                    user_prompt = result.get("prompt", "").strip()
                    ocr_text    = result.get("text", "").strip()

                    if not ocr_text:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={"chat_id": user_id, "text": "❌ Не удалось распознать текст на изображении."}
                        )
                    else:
                        # собираем финальный промпт
                        final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text

                        # 1) показываем финальный промпт
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text": f"🔄 Финальный запрос для генерации:\n{final_prompt}"
                            }
                        )

                        # 2) републикуем задачу на генерацию заданий
                        new_task = {
                            "type": "generate_tasks",
                            "user_id": user_id,
                            "student_id": result.get("student_id"),
                            "prompt": final_prompt
                        }
                        if publish_exchange:
                            await publish_exchange.publish(
                                aio_pika.Message(body=json.dumps(new_task).encode()),
                                routing_key=config.TASK_QUEUE
                            )
                        else:
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

                        # 3) уведомляем о старте генерации
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={"chat_id": user_id, "text": "🕔 Генерируются задания, ожидайте..."}
                        )

                else:
                    logging.warning(f"❓ Неизвестный тип результата: {result_type}")

            logging.info(f"📨 Результат отправлен пользователю={user_id} type={result_type}")

        except Exception:
            logging.exception("🔴 Ошибка при отправке в Telegram")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")

    # 1) PostgreSQL
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    # 2) Redis
    await redis_cache.init_redis_pool(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_DB)

    # 3) RabbitMQ
    connection = await aio_pika.connect_robust(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        login=config.RABBITMQ_USER,
        password=config.RABBITMQ_PASS,
    )
    channel = await connection.channel()
    global publish_exchange
    publish_exchange = channel.default_exchange

    logging.info("✔️ Подключение к RabbitMQ установлено")

    # 4) Объявляем очередь задач
    await channel.declare_queue(config.TASK_QUEUE, durable=True)
    logging.info(f"🕸 Объявлена очередь: {config.TASK_QUEUE}")

    # 5) Подписка
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(config.TASK_QUEUE, durable=True)
    await queue.consume(handle_message)
    logging.info(f"✅ Подписка на очередь '{config.TASK_QUEUE}' выполнена. Ожидаю задач...")

    # 6) Не завершаемся
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())