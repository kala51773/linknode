from typing import Any, Callable
from collections import defaultdict


class EventBus:
    """Lightweight event bus for internal publisher-subscriber decoupling."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        self._subscribers[topic].append(callback)

    def publish(self, topic: str, event: Any) -> None:
        for callback in self._subscribers[topic]:
            callback(event)
