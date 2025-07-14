from aiogram import BaseMiddleware
from aiogram.types import Update

from bot_app import database

class AuthMiddleware(BaseMiddleware):
    """Middleware to ensure the Telegram user is registered in the database."""
    async def __call__(self, handler, event: Update, data: dict):
        # If the event has a message or callback query from a user, ensure user exists in DB
        telegram_user = None
        if hasattr(event, "message") and event.message:
            telegram_user = event.message.from_user
        elif hasattr(event, "callback_query") and event.callback_query:
            telegram_user = event.callback_query.from_user
        if telegram_user:
            user_id = telegram_user.id
            # Check if user is in DB, if not, create them with their TG name
            user = await database.db.get_user_by_tg_id(user_id)
            if not user:
                # Use the Telegram first_name as initial name (or username if no first name)
                name = telegram_user.full_name or telegram_user.username or "User"
                await database.db.create_user(user_id, name)
        # proceed to next handler
        return await handler(event, data)
