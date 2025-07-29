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

        t = task_data.get("type")
        user_id = task_data.get("user_id")
        student_id = task_data.get("student_id")
        logging.info(f"▶ Received task: type={t}, user_id={user_id}, student_id={student_id}")

        # 2) Обрабатываем её
        try:
            result = await task_consumer.process_task_message(task_data)
            logging.info(f"✅ Processed task type={t}")
        except Exception:
            logging.exception(f"🔴 Error processing task type={t}")
            return

        if not result:
            logging.warning("⚠️ Handler returned None — skipping")
            return

        # 3) Готовим к отправке в Telegram
        user_id = result.get("user_id")
        result_type = result.get("type")
        if not user_id or not result_type:
            logging.warning("⚠️ Invalid result (missing user_id or type) — skipping")
            return

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
                    plan = result.get("plan_text", "(пусто)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": f"📄 План:\n{plan}",
                            "parse_mode": "HTML"
                        }
                    )

                # === Generated tasks PDF ===
                elif result_type == "tasks":
                    # Показываем финальный prompt, если он есть
                    final_prompt = result.get("prompt", "").strip()
                    if final_prompt:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": user_id,
                                "text": f"🔄 Финальный запрос для генерации:\n{final_prompt}"
                            }
                        )

                    # Ищем файл под ключами file или file_tasks
                    file_b64 = result.get("file") or result.get("file_tasks")
                    if not file_b64:
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                            json={"chat_id": user_id, "text": "⚠️ Не удалось сгенерировать PDF с заданиями"}
                        )
                    else:
                        pdf = base64.b64decode(file_b64)
                        buf = BytesIO(pdf)
                        buf.name = "Задания.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id", str(user_id))
                        form.add_field("caption", "📎 Ваши задания в PDF")
                        form.add_field("document", buf, filename=buf.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )

                # === Homework check ===
                elif result_type == "check":
                    report = result.get("report_text", "(нет отчёта)")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": f"✔️ Результаты проверки:\n{report}",
                            "parse_mode": "HTML"
                        }
                    )
                    file_b64 = result.get("file")
                    if file_b64:
                        pdf = base64.b64decode(file_b64)
                        buf = BytesIO(pdf); buf.name = "Homework_Report.pdf"
                        form = aiohttp.FormData()
                        form.add_field("chat_id", str(user_id))
                        form.add_field("caption", "📎 Отчёт в PDF")
                        form.add_field("document", buf, filename=buf.name)
                        await session.post(
                            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendDocument",
                            data=form
                        )

                # === Error message ===
                elif result_type == "error":
                    err = result.get("message", "Неизвестная ошибка")
                    await session.post(
                        f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                        json={"chat_id": user_id, "text": f"⚠️ Ошибка: {err}"}
                    )

                else:
                    logging.warning(f"❓ Unknown result type: {result_type}")

            logging.info(f"📨 Sent result to user={user_id}, type={result_type}")

        except Exception:
            logging.exception("🔴 Error sending message via Telegram")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")

    # 1) Инициализируем DB pool
    dsn = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await db.init_db_pool(dsn)

    # 2) Redis для FSM/кэша
    await redis_cache.init_redis_pool(config.REDIS_HOST, config.REDIS_PORT, config.REDIS_DB)

    # 3) Подключаемся к RabbitMQ и подписываемся на очередь
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
    logging.info(f"✅ Subscribed to queue '{config.TASK_QUEUE}', awaiting tasks...")

    # 4) Ждём вечно
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())