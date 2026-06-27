"""
Ограничитель одновременности для RSL Telegram Bot.

Две независимые гарантии, применяются вместе к каждому запросу на распознавание:

1. Одновременность на пользователя - у одного пользователя одновременно может
   выполняться не более ``user_max_concurrent`` задач распознавания.

2. Глобальная одновременность - суммарно по ВСЕМ пользователям к
   координатору/модели одновременно уходит не более ``global_max_concurrent``
   задач. Ставится равным числу параллельных инференсов, которые тянет модель
   (ручка "число воркеров").

Когда все глобальные слоты заняты, лишние запросы ждут в ограниченной очереди
размера ``global_queue_max``. Если и очередь заполнена - запрос сразу
отклоняется ("сервис перегружен, попробуйте позже").

ДОПУЩЕНИЕ ОБ ОДНОЙ РЕПЛИКЕ: все счётчики живут в памяти процесса. Это верно
только пока бот работает в одной реплике (replicaCount: 1, стратегия Recreate).
При масштабировании на >1 реплику это состояние нужно вынести в общий стор
(Redis); публичный API (acquire / stats) при этом задуман неизменным.

ПРО ДЕДЛАЙН: таймер дедлайна задачи координатора запускать только ПОСЛЕ того,
как ``acquire`` отдал результат ACQUIRED, чтобы ожидание в очереди не
засчитывалось в дедлайн.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum, auto
from typing import AsyncIterator, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class Decision(Enum):
    ACQUIRED = auto()   # можно продолжать
    USER_BUSY = auto()  # пользователь уже на пределе одновременности
    OVERLOADED = auto()  # глобальная очередь заполнена


@dataclass(frozen=True)
class Outcome:
    decision: Decision
    queued: bool = False  # True, если запрос ждал глобальный слот

    @property
    def acquired(self) -> bool:
        return self.decision is Decision.ACQUIRED


EnqueueHook = Callable[[], Awaitable[None]]


class Limiter:
    _instance: Optional["Limiter"] = None

    def __init__(
        self,
        *,
        enabled: bool = True,
        user_max_concurrent: int = 1,
        global_max_concurrent: int = 3,
        global_queue_max: int = 30,
    ) -> None:
        if global_max_concurrent < 1:
            raise ValueError("global_max_concurrent must be >= 1")
        if user_max_concurrent < 1:
            raise ValueError("user_max_concurrent must be >= 1")
        if global_queue_max < 0:
            raise ValueError("global_queue_max must be >= 0")

        self.enabled = enabled
        self.user_max_concurrent = user_max_concurrent
        self.global_max_concurrent = global_max_concurrent
        self.global_queue_max = global_queue_max

        self._sem = asyncio.Semaphore(global_max_concurrent)
        self._user_counts: dict[int, int] = {}
        self._waiting = 0
        self._running = 0

    @classmethod
    def init(cls, limits) -> "Limiter":
        cls._instance = cls(
            enabled=limits.enabled,
            user_max_concurrent=limits.user_max_concurrent,
            global_max_concurrent=limits.global_max_concurrent,
            global_queue_max=limits.global_queue_max,
        )
        logger.info(
            "Limiter initialised: enabled=%s user_max_concurrent=%s "
            "global_max_concurrent=%s global_queue_max=%s",
            cls._instance.enabled,
            cls._instance.user_max_concurrent,
            cls._instance.global_max_concurrent,
            cls._instance.global_queue_max,
        )
        return cls._instance

    @classmethod
    def instance(cls) -> "Limiter":
        if cls._instance is None:
            raise RuntimeError("Limiter is not initialised; call Limiter.init(...) first")
        return cls._instance

    @asynccontextmanager
    async def acquire(
        self,
        user_id: int,
        on_enqueue: Optional[EnqueueHook] = None,
    ) -> AsyncIterator[Outcome]:
        if not self.enabled:
            yield Outcome(Decision.ACQUIRED)
            return

        # фаза 1: на пользователя (проверка + инкремент атомарны на однопоточном asyncio)
        if self._user_counts.get(user_id, 0) >= self.user_max_concurrent:
            yield Outcome(Decision.USER_BUSY)
            return
        self._user_counts[user_id] = self._user_counts.get(user_id, 0) + 1

        acquired_global = False
        queued = False
        try:
            # фаза 2: глобальная
            if self._sem.locked():
                if self._waiting >= self.global_queue_max:
                    yield Outcome(Decision.OVERLOADED)
                    return
                queued = True
                self._waiting += 1
                try:
                    if on_enqueue is not None:
                        try:
                            await on_enqueue()
                        except Exception:
                            logger.warning("on_enqueue hook failed", exc_info=True)
                    await self._sem.acquire()
                finally:
                    self._waiting -= 1
            else:
                await self._sem.acquire()

            acquired_global = True
            self._running += 1
            yield Outcome(Decision.ACQUIRED, queued=queued)
        finally:
            if acquired_global:
                self._running -= 1
                self._sem.release()
            self._dec_user(user_id)

    def _dec_user(self, user_id: int) -> None:
        n = self._user_counts.get(user_id, 0) - 1
        if n <= 0:
            self._user_counts.pop(user_id, None)
        else:
            self._user_counts[user_id] = n

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "global_max_concurrent": self.global_max_concurrent,
            "running": self._running,
            "waiting": self._waiting,
            "global_queue_max": self.global_queue_max,
            "active_users": len(self._user_counts),
        }