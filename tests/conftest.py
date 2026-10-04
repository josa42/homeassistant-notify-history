"""Shared fixtures for Notify History tests."""

from __future__ import annotations

from typing import Any

from homeassistant.components import notify
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.notify_history.const import (
    CONF_MAX_AGE_DAYS,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_SERVICES,
    DOMAIN,
)

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the notify_history custom_component discoverable in tests."""
    yield


class RecordingNotifyEntity(notify.NotifyEntity):
    """A notify entity target that remembers what it was sent."""

    _attr_supported_features = notify.NotifyEntityFeature.TITLE

    def __init__(self, entity_id: str, fail: bool = False) -> None:
        self.entity_id = entity_id
        self._attr_unique_id = entity_id
        self.fail = fail
        self.sent: list[dict[str, Any]] = []

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        if self.fail:
            raise HomeAssistantError("tv is off")
        self.sent.append({"message": message, "title": title})


class Targets:
    """The targets the tests send to: notify.tv (entity), notify.phone and notify.broken (services)."""

    def __init__(self, tv: RecordingNotifyEntity) -> None:
        self.tv = tv
        self.phone: list[dict[str, Any]] = []


@pytest.fixture
async def targets(hass: HomeAssistant) -> Targets:
    assert await async_setup_component(hass, "notify", {})
    tv = RecordingNotifyEntity("notify.tv")
    await hass.data[notify.DATA_COMPONENT].async_add_entities([tv])
    result = Targets(tv)

    async def phone(call: ServiceCall) -> None:
        result.phone.append(dict(call.data))

    async def broken(call: ServiceCall) -> None:
        raise HomeAssistantError("phone is offline")

    hass.services.async_register(notify.DOMAIN, "phone", phone)
    hass.services.async_register(notify.DOMAIN, "broken", broken)
    return result


def make_entry(
    entities: list[str] | None = None,
    services: list[str] | None = None,
    max_age_days: int = 14,
    title: str = "Family",
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={},
        options={
            CONF_NOTIFY_ENTITIES: ["notify.tv"] if entities is None else entities,
            CONF_NOTIFY_SERVICES: ["phone"] if services is None else services,
            CONF_MAX_AGE_DAYS: max_age_days,
        },
    )


@pytest.fixture
async def setup_entry(hass: HomeAssistant, targets: Targets):
    """Set up a proxy and return its config entry."""

    async def _setup(**kwargs: Any) -> MockConfigEntry:
        entry = make_entry(**kwargs)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup
