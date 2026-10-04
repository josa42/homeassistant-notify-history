"""The websocket API the card reads from."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .conftest import Targets


async def _send(hass: HomeAssistant, text: str) -> None:
    await hass.services.async_call("notify", "family", {"message": text}, blocking=True)


async def test_list_pages(hass: HomeAssistant, targets: Targets, setup_entry, hass_ws_client):
    await setup_entry()
    for text in ("one", "two", "three"):
        await _send(hass, text)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "notify_history/list", "entity_id": "notify.family", "limit": 2})
    result = (await client.receive_json())["result"]
    assert [m["message"] for m in result["messages"]] == ["three", "two"]
    assert result["has_more"]

    await client.send_json_auto_id(
        {
            "type": "notify_history/list",
            "entity_id": "notify.family",
            "limit": 2,
            "before": result["messages"][-1]["id"],
        }
    )
    result = (await client.receive_json())["result"]
    assert [m["message"] for m in result["messages"]] == ["one"]
    assert not result["has_more"]


async def test_list_rejects_other_entities(
    hass: HomeAssistant, targets: Targets, setup_entry, hass_ws_client
):
    await setup_entry()
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "notify_history/list", "entity_id": "notify.tv"})
    response = await client.receive_json()

    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_subscribe_pushes_changes(hass: HomeAssistant, targets: Targets, setup_entry, hass_ws_client):
    await setup_entry()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "notify_history/subscribe", "entity_id": "notify.family"})
    assert (await client.receive_json())["success"]

    await _send(hass, "hello")
    added = (await client.receive_json())["event"]
    assert added["event"] == "added"
    assert added["message"]["message"] == "hello"

    await client.send_json_auto_id(
        {"type": "notify_history/delete", "entity_id": "notify.family", "message_id": added["message"]["id"]}
    )
    removed = (await client.receive_json())["event"]
    assert removed == {"event": "removed", "ids": [added["message"]["id"]]}
    assert (await client.receive_json())["success"]

    await hass.services.async_call("notify_history", "clear", {"entity_id": "notify.family"}, blocking=True)
    assert (await client.receive_json())["event"] == {"event": "cleared"}


async def test_subscribe_reports_an_unload(
    hass: HomeAssistant, targets: Targets, setup_entry, hass_ws_client
):
    entry = await setup_entry()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "notify_history/subscribe", "entity_id": "notify.family"})
    assert (await client.receive_json())["success"]

    assert await hass.config_entries.async_reload(entry.entry_id)

    assert (await client.receive_json())["event"] == {"event": "closed"}
