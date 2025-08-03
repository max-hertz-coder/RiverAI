from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing    import Callable, Dict, Any, Awaitable
from bot_app.database import db

class AuthMiddleware(BaseMiddleware):
    """
    При любом сообщении или callback:
      1) Проверяем, есть ли запись в users по telegram_id.
      2) Если нет — создаём её.
      3) Кладём запись в data['user'] для дальнейшего использования.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        telegram_id = None
        if hasattr(event, "from_user") and event.from_user:
            telegram_id = event.from_user.id

        user = None
        if telegram_id is not None:
            # 1) Пытаемся получить
            user = await db.get_user_by_tg_id(telegram_id)
            # 2) Если нет — создаём
            if user is None:
                name = getattr(event.from_user, "first_name", "") or ""
                await db.create_user(telegram_id, name)
                user = await db.get_user_by_tg_id(telegram_id)

        # 3) Сохраняем в context
        data["user"] = user
        return await handler(event, data)
