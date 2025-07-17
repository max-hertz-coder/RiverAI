# bot_app/middlewares/auth.py

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable
from bot_app.database import db

class AuthMiddleware(BaseMiddleware):
    """
    При любом сообщении или callback:
     1) Проверяем, есть ли user_id в таблице users.
     2) Если нет — создаём пользователя (с пустым именем, потом его можно обновить).
     3) Кладём запись пользователя (asyncpg.Record) в data['user'].
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Поддерживаем Message и CallbackQuery
        user = None
        telegram_id = None
        if hasattr(event, "from_user") and event.from_user:
            telegram_id = event.from_user.id

        if telegram_id:
            # 1) Попробуем найти в БД
            user = await db.get_user_by_tg_id(telegram_id)
            # 2) Если не нашли — создаём
            if user is None:
                # Для имени можно взять first_name, если event это Message
                name = getattr(event.from_user, "first_name", "") or ""
                await db.create_user(telegram_id, name)
                user = await db.get_user_by_tg_id(telegram_id)
        # Кладём в data, чтобы хэндлеры могли пользоваться
        data["user"] = user
        # Далее вызываем сам обработчик
        return await handler(event, data)
