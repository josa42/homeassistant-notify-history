"""Retention, persistence and the delete and clear services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.notify_history.const import MAX_MESSAGES
from custom_components.notify_history.history import NotifyHistory

from .conftest import Targets


def _message(message_id: str, timestamp: datetime) -> dict:
    return {
        "id": message_id,
        "timestamp": timestamp.isoformat(),
        "title": None,
        "message": message_id,
        "data": None,
        "source": "service",
        "targets": [],
    }


async def _send(hass: HomeAssistant, text: str) -> None:
    await hass.services.async_call("notify", "family", {"message": text}, blocking=True)


async def test_pages_newest_first(hass: HomeAssistant):
    history = NotifyHistory(hass, "entry", 14)
    now = datetime.now(timezone.utc)
    for i in range(5):
        history.async_add(_message(f"m{i}", now + timedelta(seconds=i)))

    page, has_more = history.messages(2)
    assert [m["id"] for m in page] == ["m4", "m3"]
    assert has_more

    page, has_more = history.messages(2, before="m3")
    assert [m["id"] for m in page] == ["m2", "m1"]
    assert has_more

    page, has_more = history.messages(2, before="m1")
    assert [m["id"] for m in page] == ["m0"]
    assert not has_more


async def test_prunes_messages_older_than_max_age(
    hass: HomeAssistant, targets: Targets, setup_entry, freezer: FrozenDateTimeFactory
):
    freezer.move_to("2026-10-01T12:00:00+00:00")
    entry = await setup_entry(max_age_days=2)
    await _send(hass, "old")
    freezer.tick(timedelta(days=1))
    await _send(hass, "new")

    freezer.tick(timedelta(days=1, hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    page, _ = entry.runtime_data.proxy.history.messages(10)
    assert [m["message"] for m in page] == ["new"]


async def test_keeps_at_most_max_messages(hass: HomeAssistant):
    history = NotifyHistory(hass, "entry", 14)
    now = datetime.now(timezone.utc)
    for i in range(MAX_MESSAGES + 5):
        history.async_add(_message(f"m{i:05}", now))

    page, has_more = history.messages(MAX_MESSAGES + 10)
    assert len(page) == MAX_MESSAGES
    assert page[-1]["id"] == "m00005"
    assert not has_more


async def test_history_survives_a_reload(hass: HomeAssistant, targets: Targets, setup_entry):
    entry = await setup_entry()
    await _send(hass, "kept")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    page, _ = entry.runtime_data.proxy.history.messages(10)
    assert [m["message"] for m in page] == ["kept"]


async def test_removing_the_entry_deletes_the_history(
    hass: HomeAssistant, targets: Targets, setup_entry, hass_storage
):
    entry = await setup_entry()
    await _send(hass, "gone")
    await hass.config_entries.async_unload(entry.entry_id)
    assert f"notify_history.{entry.entry_id}" in hass_storage

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert f"notify_history.{entry.entry_id}" not in hass_storage


async def test_delete_service(hass: HomeAssistant, targets: Targets, setup_entry):
    entry = await setup_entry()
    await _send(hass, "first")
    await _send(hass, "second")
    history = entry.runtime_data.proxy.history
    [second, first], _ = history.messages(10)

    await hass.services.async_call(
        "notify_history",
        "delete",
        {"entity_id": "notify.family", "message_id": first["id"]},
        blocking=True,
    )

    assert history.messages(10) == ([second], False)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "notify_history",
            "delete",
            {"entity_id": "notify.family", "message_id": "missing"},
            blocking=True,
        )


async def test_clear_service(hass: HomeAssistant, targets: Targets, setup_entry):
    entry = await setup_entry()
    await _send(hass, "first")

    await hass.services.async_call("notify_history", "clear", {"entity_id": "notify.family"}, blocking=True)

    assert entry.runtime_data.proxy.history.messages(10) == ([], False)
