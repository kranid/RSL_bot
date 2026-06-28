from typing import Any, Awaitable, Callable, cast

from aiogram import BaseMiddleware, Router
from aiogram.types import Message, TelegramObject

from core.database.database_helper import DatabaseHelper


class PermissionMiddleware(BaseMiddleware):
    def __init__(self, router_roles: dict):
        self.__router_roles = router_roles

    @staticmethod
    def __check_user_access(user_role:str, required_roles:list[str]) -> bool:
        return user_role in required_roles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],        
    ):
        message = cast(Message, event)
        message_text:str|None = message.text
        if message_text:
            command:str = message_text.split()[0].split("@")[0]
            if command == "/start":
                return await handler(event, data)
        assert message.from_user is not None
        user_tg_id = message.from_user.id
        current_router:Router|None = data.get("event_router")
        role_required:list[str]|None = self.__router_roles.get(current_router)
        assert role_required is not None
        user_role:str|None = await DatabaseHelper.instance().get_user_role(user_tg_id)
        if not user_role or not self.__check_user_access(
            user_role, role_required
        ):
            await message.answer(
                f"Доступ запрещен. Данная опция доступна только "
                f"для ролей: {role_required}. "
                f"Запросите соответствующую роль у администратора."
            )
            return
        return await handler(event, data)
