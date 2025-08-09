from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from typing import Union

from bot_app import config


class AdminFilter(BaseFilter):
    """
    Пропускает только сообщения/коллбеки от ADMIN_CHAT_ID.
    Использование:
        router.message(AdminFilter())(handler)
        router.callback_query(AdminFilter())(handler)
    """

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
        return bool(user_id and int(user_id) == int(config.ADMIN_CHAT_ID))
