"""The Notify History integration: each config entry is one notify proxy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TARGET,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, service
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify
import voluptuous as vol

from . import websocket_api
from .const import (
    ATTR_MESSAGE_ID,
    CONF_MAX_AGE_DAYS,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_SERVICES,
    DEFAULT_MAX_AGE_DAYS,
    DOMAIN,
    SERVICE_CLEAR,
    SERVICE_DELETE,
    SOURCE_SERVICE,
)
from .history import NotifyHistory
from .proxy import NotifyProxy

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.NOTIFY]

CARD_URL_PATH = "/notify-history/notify-history-card.js"
CARD_VERSION = "0.0.0"

PRUNE_INTERVAL = timedelta(hours=1)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

LEGACY_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DATA): dict,
    }
)


@dataclass
class NotifyHistoryRuntimeData:
    proxy: NotifyProxy
    # The legacy notify.<name> service this proxy registered, None when the
    # name was already taken.
    service_name: str | None


type NotifyHistoryConfigEntry = ConfigEntry[NotifyHistoryRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the card, the websocket API and the entity services. Called once per HA session."""
    websocket_api.async_register(hass)

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_DELETE,
        entity_domain=NOTIFY_DOMAIN,
        schema={vol.Required(ATTR_MESSAGE_ID): cv.string},
        func="async_delete_message",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CLEAR,
        entity_domain=NOTIFY_DOMAIN,
        schema=None,
        func="async_clear_history",
    )

    if hass.http is None:
        return True
    card_path = Path(__file__).parent / "www" / "notify-history-card.js"
    if not card_path.is_file():
        _LOGGER.warning("Notify history card asset missing at %s", card_path)
        return True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, str(card_path), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL_PATH}?v={CARD_VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NotifyHistoryConfigEntry) -> bool:
    """Set up one proxy."""
    history = NotifyHistory(hass, entry.entry_id, entry.options.get(CONF_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS))
    await history.async_load()
    entry.async_on_unload(async_track_time_interval(hass, history.async_prune, PRUNE_INTERVAL))

    proxy = NotifyProxy(
        hass,
        history,
        notify_entities=list(entry.options.get(CONF_NOTIFY_ENTITIES, [])),
        notify_services=list(entry.options.get(CONF_NOTIFY_SERVICES, [])),
    )
    entry.runtime_data = NotifyHistoryRuntimeData(
        proxy=proxy, service_name=_async_register_legacy_service(hass, entry, proxy)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NotifyHistoryConfigEntry) -> bool:
    """Tear down one proxy."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    if entry.runtime_data.service_name is not None:
        hass.services.async_remove(NOTIFY_DOMAIN, entry.runtime_data.service_name)
    await entry.runtime_data.proxy.history.async_flush()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the history together with the proxy."""
    await NotifyHistory(hass, entry.entry_id, DEFAULT_MAX_AGE_DAYS).async_remove()


def _async_register_legacy_service(
    hass: HomeAssistant, entry: NotifyHistoryConfigEntry, proxy: NotifyProxy
) -> str | None:
    """Register notify.<name>, so automations written for a legacy notify service can switch over."""
    name = slugify(entry.title)
    if hass.services.has_service(NOTIFY_DOMAIN, name):
        _LOGGER.warning(
            "Not registering notify.%s for %s: a service with that name already exists",
            name,
            entry.title,
        )
        return None

    async def handle(call: ServiceCall) -> None:
        await proxy.async_send(
            message=call.data[ATTR_MESSAGE],
            title=call.data.get(ATTR_TITLE),
            data=call.data.get(ATTR_DATA),
            target=call.data.get(ATTR_TARGET),
            source=SOURCE_SERVICE,
            context=call.context,
        )

    hass.services.async_register(NOTIFY_DOMAIN, name, handle, schema=LEGACY_SERVICE_SCHEMA)
    return name
