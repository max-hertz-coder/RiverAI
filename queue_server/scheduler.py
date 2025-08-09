"""
Scheduler заглушка.

В данной конфигурации распределение задач выполняет сам RabbitMQ:
  • воркеры подписываются на очереди задач (task_queue);
  • бот подписывается на очередь результатов (result_queue).

Если позже потребуется кастомный роутинг (приоритеты, шейпинг нагрузки, фан-аут, ретраи),
здесь можно реализовать диспетчеризацию поверх RabbitMQ.

Оставлено намеренно, чтобы не ломать импорты и пайплайны.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self):
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("Scheduler is idle (routing handled by RabbitMQ).")
        try:
            while self._running:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        self._running = False
