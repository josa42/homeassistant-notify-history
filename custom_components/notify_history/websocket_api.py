"""Websocket API behind the notify history card.

Every command takes the proxy's notify entity, the handle the card is
configured with. `notify_history/subscribe` pushes each change so the card
does not have to poll.
"""

from __future__ import annotations

from typing import Any

from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .const import DOMAIN
from .history import HistoryEvent, NotifyHistory

DEFAULT_LIMIT = 20
MAX_LIMIT = 200


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_delete)


def _history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any], policy: str
) -> NotifyHistory | None:
    """Resolve the history behind msg["entity_id"], or send an error and return None."""
    entity_id = msg["entity_id"]
    if not connection.user.permissions.check_entity(entity_id, policy):
        raise Unauthorized(entity_id=entity_id)
    reg_entry = er.async_get(hass).async_get(entity_id)
    config_entry = (
        hass.config_entries.async_get_entry(reg_entry.config_entry_id)
        if reg_entry is not None and reg_entry.platform == DOMAIN and reg_entry.config_entry_id
        else None
    )
    if config_entry is None or config_entry.state is not ConfigEntryState.LOADED:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, f"{entity_id} is not a notify history proxy"
        )
        return None
    return config_entry.runtime_data.proxy.history


@websocket_api.websocket_command(
    {
        vol.Required("type"): "notify_history/list",
        vol.Required("entity_id"): str,
        vol.Optional("limit", default=DEFAULT_LIMIT): vol.All(int, vol.Range(min=1, max=MAX_LIMIT)),
        vol.Optional("before"): str,
    }
)
@callback
def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Return a page of messages, newest first. Pass the last id as `before` for the next page."""
    if (history := _history(hass, connection, msg, POLICY_READ)) is None:
        return
    messages, has_more = history.messages(msg["limit"], msg.get("before"))
    connection.send_result(msg["id"], {"messages": messages, "has_more": has_more})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "notify_history/subscribe",
        vol.Required("entity_id"): str,
    }
)
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Push every added, removed or cleared event of one proxy."""
    if (history := _history(hass, connection, msg, POLICY_READ)) is None:
        return

    @callback
    def forward(event: HistoryEvent) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], event))

    connection.subscriptions[msg["id"]] = history.async_subscribe(forward)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "notify_history/delete",
        vol.Required("entity_id"): str,
        vol.Required("message_id"): str,
    }
)
@callback
def ws_delete(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    if (history := _history(hass, connection, msg, POLICY_CONTROL)) is None:
        return
    if not history.async_delete(msg["message_id"]):
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Message not found")
        return
    connection.send_result(msg["id"])
