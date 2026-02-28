"""CozyLife integration."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EFFECT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, CONF_DEVICE_TYPE_CODE, PLATFORMS_BY_TYPE
from .tcp_client import tcp_client

_LOGGER = logging.getLogger(__name__)

# Key for storing light entity references for set_all_effect service
LIGHT_ENTITIES_KEY = "light_entities"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the CozyLife component (YAML import handled per-platform)."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(LIGHT_ENTITIES_KEY, [])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a CozyLife device from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(LIGHT_ENTITIES_KEY, [])

    data = entry.data
    client = tcp_client(data["ip"])
    client._device_id = data["did"]
    client._pid = data["pid"]
    client._dpid = data["dpid"]
    client._device_model_name = data.get("dmn", "CozyLife Device")
    client._device_type_code = data.get(CONF_DEVICE_TYPE_CODE, "01")

    await hass.async_add_executor_job(client._initSocket)

    hass.data[DOMAIN][entry.entry_id] = client

    device_type = data.get(CONF_DEVICE_TYPE_CODE, "01")
    platform = PLATFORMS_BY_TYPE.get(device_type, "light")
    await hass.config_entries.async_forward_entry_setups(entry, [platform])

    # Register domain-level set_all_effect service (once)
    if not hass.services.has_service(DOMAIN, "set_all_effect"):
        async def async_set_all_effect(call: ServiceCall) -> None:
            effect = call.data.get(CONF_EFFECT)
            for entity in hass.data[DOMAIN].get(LIGHT_ENTITIES_KEY, []):
                await entity.async_set_effect(effect)
                await asyncio.sleep(0.01)

        hass.services.async_register(
            DOMAIN,
            "set_all_effect",
            async_set_all_effect,
            schema=vol.Schema(
                {vol.Required(CONF_EFFECT): vol.In(
                    ["manual", "natural", "sleep", "warm", "study", "chrismas"]
                )}
            ),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a CozyLife config entry."""
    data = entry.data
    device_type = data.get(CONF_DEVICE_TYPE_CODE, "01")
    platform = PLATFORMS_BY_TYPE.get(device_type, "light")

    ok = await hass.config_entries.async_unload_platforms(entry, [platform])
    if ok:
        client = hass.data[DOMAIN].pop(entry.entry_id, None)
        if client:
            await hass.async_add_executor_job(client.disconnect)

    return ok
