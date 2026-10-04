"""The message history of one proxy, persisted in its own store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MAX_MESSAGES

STORAGE_VERSION = 1
SAVE_DELAY = 1

type Message = dict[str, Any]
type HistoryEvent = dict[str, Any]
type HistoryListener = Callable[[HistoryEvent], None]


class NotifyHistory:
    """Keeps the messages of one proxy, oldest first, and tells listeners about changes.

    Listeners get one of:
    - {"event": "added", "message": <message>}
    - {"event": "removed", "ids": [<id>, ...]}
    - {"event": "cleared"}
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, max_age_days: int) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._max_age = timedelta(days=max_age_days)
        self._messages: list[Message] = []
        self._listeners: list[HistoryListener] = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._messages = list((data or {}).get("messages", []))
        self.async_prune()

    async def async_flush(self) -> None:
        await self._store.async_save(self._data())

    async def async_remove(self) -> None:
        await self._store.async_remove()

    def messages(self, limit: int, before: str | None = None) -> tuple[list[Message], bool]:
        """Return up to `limit` messages, newest first, older than the message `before`."""
        newest_first = list(reversed(self._messages))
        if before is not None:
            index = next((i for i, m in enumerate(newest_first) if m["id"] == before), None)
            newest_first = [] if index is None else newest_first[index + 1 :]
        return newest_first[:limit], len(newest_first) > limit

    def get(self, message_id: str) -> Message | None:
        return next((m for m in self._messages if m["id"] == message_id), None)

    @callback
    def async_add(self, message: Message) -> None:
        self._messages.append(message)
        self._notify({"event": "added", "message": message})
        self.async_prune()
        self._save()

    @callback
    def async_delete(self, message_id: str) -> bool:
        if self.get(message_id) is None:
            return False
        self._remove({message_id})
        return True

    @callback
    def async_clear(self) -> None:
        self._messages = []
        self._notify({"event": "cleared"})
        self._save()

    @callback
    def async_prune(self, *_: Any) -> None:
        """Drop messages older than the max age, and the oldest beyond MAX_MESSAGES."""
        cutoff = (dt_util.utcnow() - self._max_age).isoformat()
        expired = {m["id"] for m in self._messages if m["timestamp"] < cutoff}
        kept = [m for m in self._messages if m["id"] not in expired]
        expired |= {m["id"] for m in kept[: max(0, len(kept) - MAX_MESSAGES)]}
        if expired:
            self._remove(expired)

    @callback
    def async_subscribe(self, listener: HistoryListener) -> Callable[[], None]:
        self._listeners.append(listener)

        @callback
        def unsubscribe() -> None:
            self._listeners.remove(listener)

        return unsubscribe

    def _remove(self, ids: set[str]) -> None:
        self._messages = [m for m in self._messages if m["id"] not in ids]
        self._notify({"event": "removed", "ids": sorted(ids)})
        self._save()

    def _notify(self, event: HistoryEvent) -> None:
        for listener in list(self._listeners):
            listener(event)

    def _save(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def _data(self) -> dict[str, Any]:
        return {"messages": self._messages}
