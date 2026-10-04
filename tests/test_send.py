"""Sending through the notify entity and the legacy notify.<name> service."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest

from .conftest import Targets


def _history(entry):
    return entry.runtime_data.proxy.history


async def test_entity_forwards_message_and_title(hass: HomeAssistant, targets: Targets, setup_entry):
    entry = await setup_entry()

    await hass.services.async_call(
        "notify",
        "send_message",
        {"entity_id": "notify.family", "message": "Dinner", "title": "Kitchen"},
        blocking=True,
    )

    assert targets.tv.sent == [{"message": "Dinner", "title": "Kitchen"}]
    assert targets.phone == [{"message": "Dinner", "title": "Kitchen"}]

    [message], has_more = _history(entry).messages(10)
    assert not has_more
    assert message["message"] == "Dinner"
    assert message["title"] == "Kitchen"
    assert message["data"] is None
    assert message["source"] == "entity"
    assert message["targets"] == [
        {"type": "entity", "id": "notify.tv", "status": "ok"},
        {"type": "service", "id": "notify.phone", "status": "ok"},
    ]
    assert dt_util.parse_datetime(hass.states.get("notify.family").state) is not None


async def test_legacy_service_forwards_data_and_target_to_services_only(
    hass: HomeAssistant, targets: Targets, setup_entry
):
    entry = await setup_entry()
    assert hass.states.get("notify.family").state == "unknown"

    await hass.services.async_call(
        "notify",
        "family",
        {"message": "Door open", "title": "Alarm", "data": {"tag": "door"}, "target": "device"},
        blocking=True,
    )

    assert targets.tv.sent == [{"message": "Door open", "title": "Alarm"}]
    assert targets.phone == [
        {"message": "Door open", "title": "Alarm", "data": {"tag": "door"}, "target": ["device"]}
    ]
    [message], _ = _history(entry).messages(10)
    assert message["source"] == "service"
    assert message["data"] == {"tag": "door"}
    # The entity reports the last message, whichever way it was sent.
    assert dt_util.parse_datetime(hass.states.get("notify.family").state) is not None


async def test_one_failing_target_is_recorded_without_raising(
    hass: HomeAssistant, targets: Targets, setup_entry
):
    entry = await setup_entry(services=["phone", "broken"])

    await hass.services.async_call("notify", "family", {"message": "Hi"}, blocking=True)

    assert targets.phone == [{"message": "Hi"}]
    [message], _ = _history(entry).messages(10)
    assert message["targets"][-1] == {
        "type": "service",
        "id": "notify.broken",
        "status": "error",
        "error": "phone is offline",
    }


async def test_all_targets_failing_raises_and_still_records(
    hass: HomeAssistant, targets: Targets, setup_entry
):
    targets.tv.fail = True
    entry = await setup_entry(services=["broken"])

    with pytest.raises(HomeAssistantError, match="every target"):
        await hass.services.async_call("notify", "family", {"message": "Hi"}, blocking=True)

    [message], _ = _history(entry).messages(10)
    assert [t["status"] for t in message["targets"]] == ["error", "error"]


async def test_legacy_service_is_skipped_when_the_name_is_taken(
    hass: HomeAssistant, targets: Targets, setup_entry
):
    entry = await setup_entry(title="Phone", services=[])

    assert entry.runtime_data.service_name is None
    # The existing service still goes to the phone, not the proxy.
    await hass.services.async_call("notify", "phone", {"message": "Hi"}, blocking=True)
    assert targets.phone == [{"message": "Hi"}]
    assert _history(entry).messages(10) == ([], False)


async def test_unload_removes_the_legacy_service(hass: HomeAssistant, targets: Targets, setup_entry):
    entry = await setup_entry()
    assert hass.services.has_service("notify", "family")

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert not hass.services.has_service("notify", "family")
