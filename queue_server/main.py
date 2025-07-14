import asyncio
import logging
import signal

from aiohttp import web

from broker import RabbitBroker
from scheduler import Scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP health-check endpoint
async def handle_health(request):
    return web.Response(text="OK")

async def start_health_server(host: str = "0.0.0.0", port: int = 8000):
    app = web.Application()
    app.router.add_get("/healthz", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    logger.info(f"Starting health-check server on http://{host}:{port}/healthz")
    await site.start()
    return runner

async def main():
    # 1. Connect to RabbitMQ
    broker = RabbitBroker()
    await broker.connect()
    logger.info("Connected to RabbitMQ broker")

    # 2. Create and start the scheduler loop
    scheduler = Scheduler(broker)
    scheduler_task = asyncio.create_task(scheduler.run())
    logger.info("Scheduler started")

    # 3. Start HTTP health-check server
    health_runner = await start_health_server()

    # 4. Wait for shutdown signal (SIGINT or SIGTERM)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()
    logger.info("Shutdown signal received, stopping services...")

    # 5. Gracefully cancel scheduler and HTTP server
    scheduler_task.cancel()
    await asyncio.gather(scheduler_task, return_exceptions=True)

    await health_runner.cleanup()
    logger.info("Health-check server stopped")

    # 6. Disconnect from RabbitMQ
    await broker.close()
    logger.info("Disconnected from RabbitMQ broker")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Queue server terminated")
