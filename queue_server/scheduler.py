import asyncio
import json
import logging
import aio_pika

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Scheduler: принимает задачи от бота, кладёт их во внутреннюю очередь,
    распределяет их воркерам и перенаправляет обратно результаты.
    """

    def __init__(self, broker):
        self.broker = broker
        self.pending_tasks: asyncio.Queue = asyncio.Queue()

    async def run(self):
        """
        Запускает приём задач, их рассылку воркерам и пересылку результатов боту.
        """
        await asyncio.gather(
            self._consume_tasks_loop(),
            self._dispatch_loop(),
            self._process_results_loop(),
        )

    async def _consume_tasks_loop(self):
        """
        Слушает очередь задач от бота и кладёт каждую задачу во внутреннюю очередь.
        """
        async def on_task(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    payload = message.body.decode()
                    task = json.loads(payload)
                    task_id = task.get("task_id", "<no-id>")
                    logger.info(f"[Scheduler] Received task id={task_id} type={task.get('type')}")
                    await self.pending_tasks.put(task)
                except Exception as e:
                    logger.error(f"[Scheduler] Error parsing incoming task: {e}")

        # broker.consume_tasks настраивает подписку на RabbitMQ-очередь задач
        await self.broker.consume_tasks(on_task)

    async def _dispatch_loop(self):
        """
        Берёт задачу из внутренней очереди и отправляет её воркерам.
        """
        while True:
            task = await self.pending_tasks.get()
            try:
                body = json.dumps(task).encode()
                await self.broker.publish_task(body)
                logger.info(f"[Scheduler] Dispatched task id={task.get('task_id')} type={task.get('type')}")
            except Exception as e:
                logger.error(f"[Scheduler] Failed to dispatch task {task.get('task_id')}: {e}")
            finally:
                self.pending_tasks.task_done()

    async def _process_results_loop(self):
        """
        Слушает очередь результатов от воркеров и пересылает их боту.
        """
        async def on_result(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    payload = message.body  # уже байты JSON
                    result = json.loads(payload.decode())
                    task_id = result.get("task_id", "<no-id>")
                    logger.info(f"[Scheduler] Received result for task id={task_id}")
                    # Пересылаем результат в очередь бота
                    await self.broker.publish_result(payload)
                    logger.info(f"[Scheduler] Forwarded result id={task_id} to bot")
                except Exception as e:
                    logger.error(f"[Scheduler] Error processing result: {e}")

        # broker.consume_results настраивает подписку на очередь результатов воркеров
        await self.broker.consume_results(on_result)
