# bot_app/result_consumer.py
import asyncio
import logging
from aiogram import Bot

from bot_app.rabbit import start_result_consumer
from bot_app.redis_result_consumer import consume_redis_results

logger = logging.getLogger(__name__)


async def run_result_consumers(bot: Bot) -> None:
    """
    Запускает одновременно:
      - AMQP consumer (RabbitMQ RESULT_QUEUE)
      - Redis poller (по ключам result:*)
    """
    logger.info("🚀 Starting result consumers…")
    tasks = [
        asyncio.create_task(start_result_consumer(bot), name="amqp_result_consumer"),
        asyncio.create_task(consume_redis_results(bot), name="redis_result_poller"),
    ]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for t in done:
        try:
            t.result()
        except Exception as e:
            logger.exception("Result consumer crashed: %s", e)
    for t in pending:
        t.cancel()
