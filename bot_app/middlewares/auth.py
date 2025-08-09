from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot_app.database import db


class AuthMiddleware(BaseMiddleware):
    """
    На каждом апдейте:
      1) Проверяем наличие пользователя в БД по telegram_id.
      2) Если нет — создаём (trial-профиль).
      3) Кладём запись в data['user'].
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        telegram_id = getattr(getattr(event, "from_user", None), "id", None)

        user = None
        if telegram_id is not None:
            user = await db.get_user_by_tg_id(telegram_id)
            if user is None:
                name = getattr(getattr(event, "from_user", None), "first_name", "") or ""
                await db.create_user(telegram_id, name)
                user = await db.get_user_by_tg_id(telegram_id)

        data["user"] = user
        return await handler(event, data)
