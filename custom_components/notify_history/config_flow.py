"""Config flow for Notify History: each proxy is its own config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN, SERVICE_SEND_MESSAGE
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.util import slugify
import voluptuous as vol

from .const import (
    CONF_MAX_AGE_DAYS,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_SERVICES,
    DEFAULT_MAX_AGE_DAYS,
    DOMAIN,
)


def _own_services(hass: HomeAssistant) -> set[str]:
    return {
        entry.runtime_data.service_name
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry.runtime_data.service_name is not None
    }


def _targets_schema(hass: HomeAssistant, selected_services: list[str]) -> dict[Any, Any]:
    """Target and retention fields, leaving out the proxies themselves so none can loop."""
    own_entities = [e.entity_id for e in er.async_get(hass).entities.values() if e.platform == DOMAIN]
    services = set(hass.services.async_services_for_domain(NOTIFY_DOMAIN))
    services -= {SERVICE_SEND_MESSAGE, *_own_services(hass)}
    # Keep a selected service that is gone for now, e.g. its integration is
    # still starting, so saving the options does not drop it.
    services |= set(selected_services)

    return {
        vol.Optional(CONF_NOTIFY_ENTITIES, default=[]): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=NOTIFY_DOMAIN, multiple=True, exclude_entities=own_entities)
        ),
        vol.Optional(CONF_NOTIFY_SERVICES, default=[]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=sorted(services),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_MAX_AGE_DAYS, default=DEFAULT_MAX_AGE_DAYS): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=365, step=1, unit_of_measurement="d", mode=selector.NumberSelectorMode.BOX
            )
        ),
    }


def _validate_targets(user_input: dict[str, Any]) -> dict[str, str]:
    if not user_input.get(CONF_NOTIFY_ENTITIES) and not user_input.get(CONF_NOTIFY_SERVICES):
        return {"base": "no_targets"}
    return {}


def _options(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_NOTIFY_ENTITIES: user_input.get(CONF_NOTIFY_ENTITIES, []),
        CONF_NOTIFY_SERVICES: user_input.get(CONF_NOTIFY_SERVICES, []),
        CONF_MAX_AGE_DAYS: int(user_input[CONF_MAX_AGE_DAYS]),
    }


class NotifyHistoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one proxy per config entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NotifyHistoryOptionsFlow:
        return NotifyHistoryOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_targets(user_input)
            name = user_input[CONF_NAME]
            if self.hass.services.has_service(NOTIFY_DOMAIN, slugify(name)):
                errors[CONF_NAME] = "name_taken"
            if not errors:
                return self.async_create_entry(title=name, data={}, options=_options(user_input))

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                **_targets_schema(self.hass, []),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )


class NotifyHistoryOptionsFlow(OptionsFlowWithReload):
    """Change the targets and the max age of a proxy."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_targets(user_input)
            if not errors:
                return self.async_create_entry(data=_options(user_input))

        current = user_input or dict(self.config_entry.options)
        schema = vol.Schema(_targets_schema(self.hass, current.get(CONF_NOTIFY_SERVICES, [])))
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
            errors=errors,
        )
