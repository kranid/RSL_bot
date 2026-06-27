from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from cachetools import TTLCache

logger = logging.getLogger(__name__)


_MAX_TRACKED_USERS = 10_000


class FloodGuardMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        enabled: bool = True,
        max_events: int = 20,
        window_seconds: int = 10,
        mute_seconds: int = 300,
        notify: bool = True,
    ) -> None:
        self.enabled = enabled
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.mute_seconds = mute_seconds
        self.notify = notify


        self._events: TTLCache[int, list[float]] = TTLCache(
            maxsize=_MAX_TRACKED_USERS, ttl=max(window_seconds * 2, 1)
        )
        # Замьюченные; записи истекают через mute_seconds (авто-размьют).
        self._muted: TTLCache[int, bool] = TTLCache(
            maxsize=_MAX_TRACKED_USERS, ttl=max(mute_seconds, 1)
        )
        # Уведомление "доступ ограничен" шлем не чаще раза за окно мьюта.
        self._notified: TTLCache[int, bool] = TTLCache(
            maxsize=_MAX_TRACKED_USERS, ttl=max(mute_seconds, 1)
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.enabled:
            return await handler(event, data)

        uid = self._get_user_id(event, data)
        if uid is None:
            # Служебные апдейты без пользователя пропускаем.
            return await handler(event, data)

        # Уже замьючен -> молча отбрасываем .
        if uid in self._muted:
            return None

        now = time.monotonic()
        cutoff = now - self.window_seconds
        stamps = [t for t in self._events.get(uid, ()) if t >= cutoff]
        stamps.append(now)
        self._events[uid] = stamps

        if len(stamps) > self.max_events:
            self._muted[uid] = True
            logger.warning(
                "flood guard muted user %s (%s events within %ss) for %ss",
                uid,
                len(stamps),
                self.window_seconds,
                self.mute_seconds,
            )
            if self.notify and uid not in self._notified:
                self._notified[uid] = True
                await self._notify_blocked(event)
            return None

        return await handler(event, data)

    @staticmethod
    def _get_user_id(event: TelegramObject, data: dict[str, Any]) -> Optional[int]:
        user = data.get("event_from_user")
        uid = getattr(user, "id", None)
        if isinstance(uid, int):
            return uid
        if isinstance(event, Message) and event.from_user is not None:
            return event.from_user.id
        if isinstance(event, CallbackQuery):
            return event.from_user.id
        return None

    async def _notify_blocked(self, event: TelegramObject) -> None:
        text = (
            f"Слишком много запросов. Доступ ограничен на {self.mute_seconds} секунд., "
            f"попробуйте позже."
        )
        try:
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=False)
        except Exception:
            logger.debug("flood notify failed", exc_info=True)
