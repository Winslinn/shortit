from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UserRegisteredEvent:
    user_id: int
    email: str
    registered_at: str
    provider: str

class UserRegisteredObserver(Protocol):
    async def on_user_registered(self, event: UserRegisteredEvent) -> None: ...

class UserRegisteredPublisher(Protocol):
    async def publish(self, event: UserRegisteredEvent) -> None: ...

class RegistrationAuditObserver:
    async def on_user_registered(self, event: UserRegisteredEvent) -> None:
        logger.info(
            "User registration completed",
            extra={"user_id": event.user_id, "provider": event.provider},
        )

class ObserverDispatcher:
    def __init__(self) -> None:
        self._observers: list[UserRegisteredObserver] = []

    def subscribe(self, observer: UserRegisteredObserver) -> None:
        self._observers.append(observer)

    async def publish(self, event: UserRegisteredEvent) -> None:
        observers = tuple(self._observers)
        if not observers:
            return

        results = await asyncio.gather(
            *(observer.on_user_registered(event) for observer in observers),
            return_exceptions=True,
        )
        for observer, result in zip(observers, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "User registration observer failed",
                    extra={
                        "observer": type(observer).__name__,
                        "user_id": event.user_id,
                    },
                    exc_info=(type(result), result, result.__traceback__),
                )

registration_observers = ObserverDispatcher()
registration_observers.subscribe(RegistrationAuditObserver())
_user_registered_publisher: UserRegisteredPublisher = registration_observers

def configure_user_registered_publisher(publisher: UserRegisteredPublisher) -> None:
    global _user_registered_publisher
    _user_registered_publisher = publisher

async def publish_user_registered(event: UserRegisteredEvent) -> None:
    try:
        await _user_registered_publisher.publish(event)
    except Exception:
        logger.exception(
            "Could not publish user registration event",
            extra={"user_id": event.user_id},
        )