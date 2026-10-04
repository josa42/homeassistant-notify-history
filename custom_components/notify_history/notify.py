"""The notify entity of a proxy."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NotifyHistoryConfigEntry
from .const import DOMAIN, SOURCE_ENTITY, SOURCE_SERVICE
from .history import HistoryEvent
from .proxy import NotifyProxy


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NotifyHistoryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NotifyHistoryEntity(entry.entry_id, entry.title, entry.runtime_data.proxy)])


class NotifyHistoryEntity(NotifyEntity):
    """Sends through the proxy, and owns the delete and clear services."""

    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry_id: str, name: str, proxy: NotifyProxy) -> None:
        self._attr_unique_id = entry_id
        self._attr_name = name
        self._proxy = proxy

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._proxy.history.async_subscribe(self._on_history_event))

    @callback
    def _on_history_event(self, event: HistoryEvent) -> None:
        # The base class records messages sent through the entity itself; this
        # keeps the state current for those sent through notify.<name> too.
        if event["event"] == "added" and event["message"]["source"] == SOURCE_SERVICE:
            self._async_record_notification()

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        await self._proxy.async_send(
            message=message,
            title=title,
            data=None,
            target=None,
            source=SOURCE_ENTITY,
            context=self._context,
        )

    async def async_delete_message(self, message_id: str) -> None:
        if not self._proxy.history.async_delete(message_id):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="message_not_found",
                translation_placeholders={"message_id": message_id},
            )

    async def async_clear_history(self) -> None:
        self._proxy.history.async_clear()
