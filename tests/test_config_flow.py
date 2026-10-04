"""Config and options flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.notify_history.const import DOMAIN

from .conftest import Targets


def _service_options(result) -> list[str]:
    for key, value in result["data_schema"].schema.items():
        if key == "notify_services":
            return value.config["options"]
    raise AssertionError("no notify_services field")


async def test_creates_a_proxy(hass: HomeAssistant, targets: Targets):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert _service_options(result) == ["broken", "persistent_notification", "phone"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Family",
            "notify_entities": ["notify.tv"],
            "notify_services": ["phone"],
            "max_age_days": 7,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Family"
    assert result["options"] == {
        "notify_entities": ["notify.tv"],
        "notify_services": ["phone"],
        "max_age_days": 7,
    }
    await hass.async_block_till_done()
    assert hass.services.has_service("notify", "family")


async def test_requires_a_target(hass: HomeAssistant, targets: Targets):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Family", "max_age_days": 14}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_targets"}


async def test_rejects_a_taken_service_name(hass: HomeAssistant, targets: Targets):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Phone", "notify_services": ["broken"], "max_age_days": 14}
    )

    assert result["errors"] == {"name": "name_taken"}


async def test_does_not_offer_proxies_as_targets(hass: HomeAssistant, targets: Targets, setup_entry):
    await setup_entry()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert "family" not in _service_options(result)


async def test_options_change_the_targets(hass: HomeAssistant, targets: Targets, setup_entry):
    entry = await setup_entry()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_entities": [], "notify_services": ["phone"], "max_age_days": 3}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.runtime_data.proxy.notify_entities == []

    await hass.services.async_call("notify", "family", {"message": "Hi"}, blocking=True)
    assert targets.tv.sent == []
    assert targets.phone == [{"message": "Hi"}]
