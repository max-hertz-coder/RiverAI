import asyncio
import json

class Scheduler:
    def __init__(self, broker):
        self.broker = broker
        self.pending_tasks = asyncio.Queue()  # очередь задач в памяти
        self.results = {}  # по task_id -> результат

    async def run(self):
        # Запускаем параллельно обработку задач и результатов
        await asyncio.gather(
            self.process_incoming_tasks(),
            self.process_results()
        )

    async def process_incoming_tasks(self):
        # Получаем задачи из RabbitMQ и ставим в локальную очередь
        async def on_task(message: aio_pika.IncomingMessage):
            async with message.process():
                body = message.body
                task = json.loads(body.decode())
                task_id = task.get("task_id")
                print(f"Task received: {task_id}")
                await self.pending_tasks.put(task)
        await self.broker.consume_tasks(on_task)

    async def process_results(self):
        # Получаем результаты из RabbitMQ
        async def on_result(message: aio_pika.IncomingMessage):
            async with message.process():
                body = message.body
                result = json.loads(body.decode())
                task_id = result.get("task_id")
                print(f"Result received for task: {task_id}")
                self.results[task_id] = result
        await self.broker.consume_results(on_result)

    async def dispatch_task_to_worker(self):
        # Берём задачу из очереди и отправляем воркеру
        while True:
            task = await self.pending_tasks.get()
            # Здесь логика выбора воркера (по нагрузке, случайно, по типу задачи и т.д.)
            # В нашем RabbitMQ - просто отправляем задачу обратно в очередь (или другой exchange)
            await self.broker.publish_task(json.dumps(task).encode())
            print(f"Task dispatched: {task.get('task_id')}")
            await asyncio.sleep(0)  # пропуск управления
