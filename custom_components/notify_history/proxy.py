"""Forwards a message to every target of a proxy and records it."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TARGET,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from .const import DOMAIN, STATUS_ERROR, STATUS_OK
from .history import Message, NotifyHistory

_LOGGER = logging.getLogger(__name__)

TARGET_ENTITY = "entity"
TARGET_SERVICE = "service"


@dataclass
class NotifyProxy:
    """One proxy: its targets and its history."""

    hass: HomeAssistant
    history: NotifyHistory
    notify_entities: list[str] = field(default_factory=list)
    notify_services: list[str] = field(default_factory=list)

    async def async_send(
        self,
        *,
        message: str,
        title: str | None,
        data: dict[str, Any] | None,
        target: list[str] | None,
        source: str,
        context: Context | None,
    ) -> Message:
        """Send to all targets at once, record the outcome of each, then store the message.

        Raises only when every target failed: one unreachable phone should not
        stop the automation that notifies three.
        """
        calls: list[tuple[dict[str, str], Any]] = []
        for entity_id in self.notify_entities:
            payload: dict[str, Any] = {ATTR_ENTITY_ID: entity_id, ATTR_MESSAGE: message}
            if title is not None:
                payload[ATTR_TITLE] = title
            calls.append(
                (
                    {"type": TARGET_ENTITY, "id": entity_id},
                    self._call(SERVICE_SEND_MESSAGE, payload, context),
                )
            )
        for service in self.notify_services:
            payload = {ATTR_MESSAGE: message}
            if title is not None:
                payload[ATTR_TITLE] = title
            if data:
                payload[ATTR_DATA] = data
            if target:
                payload[ATTR_TARGET] = target
            calls.append(
                (
                    {"type": TARGET_SERVICE, "id": f"{NOTIFY_DOMAIN}.{service}"},
                    self._call(service, payload, context),
                )
            )

        results = await asyncio.gather(*(call for _, call in calls), return_exceptions=True)

        targets: list[dict[str, Any]] = []
        for (ref, _), result in zip(calls, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Sending to %s failed: %s", ref["id"], result)
                targets.append({**ref, "status": STATUS_ERROR, "error": str(result) or type(result).__name__})
            else:
                targets.append({**ref, "status": STATUS_OK})

        record: Message = {
            "id": ulid_now(),
            "timestamp": dt_util.utcnow().isoformat(),
            "title": title,
            "message": message,
            "data": data or None,
            "source": source,
            "targets": targets,
        }
        self.history.async_add(record)

        if targets and all(t["status"] == STATUS_ERROR for t in targets):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="all_targets_failed",
                translation_placeholders={"errors": "; ".join(f"{t['id']}: {t['error']}" for t in targets)},
            )
        return record

    async def _call(self, service: str, payload: dict[str, Any], context: Context | None) -> None:
        await self.hass.services.async_call(NOTIFY_DOMAIN, service, payload, blocking=True, context=context)
