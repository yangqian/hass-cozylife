"""Platform for CozyLife switch integration."""
from __future__ import annotations
import logging
from .tcp_client import tcp_client
from datetime import timedelta
import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from typing import Any
from .const import (
    DOMAIN,
    SWITCH_TYPE_CODE,
    CONF_DEVICE_TYPE_CODE,
)

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

SCAN_INTERVAL = timedelta(seconds=240)

_LOGGER = logging.getLogger(__name__)

SWITCH_SCHEMA = vol.Schema({
    vol.Required('ip'): cv.string,
    vol.Required('did'): cv.string,
    vol.Optional('dmn', default='Smart Switch'): cv.string,
    vol.Optional('name'): cv.string,
    vol.Optional('pid', default='p93sfg'): cv.string,
    vol.Optional('dpid', default=[1]):
        vol.All(cv.ensure_list, [int])
})

from homeassistant.components.switch import PLATFORM_SCHEMA
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('switches', default=[]):
        vol.All(cv.ensure_list, [SWITCH_SCHEMA])
})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CozyLife switches from a hub config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    clients = entry_data["clients"]
    devices = entry_data["devices"]

    entities = []
    for dev in devices:
        device_type = dev.get(CONF_DEVICE_TYPE_CODE, "01")
        if device_type != SWITCH_TYPE_CODE:
            continue
        client = clients.get(dev["did"])
        if client is None:
            continue
        entity = CozyLifeSwitch(client, hass)
        entities.append(entity)

    if entities:
        async_add_entities(entities)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Import YAML configuration as config entries."""
    _LOGGER.warning(
        "Configuration of CozyLife switches via YAML is deprecated. "
        "Your YAML config has been imported. Please remove it."
    )
    for item in config.get('switches', []):
        import_data = {
            "ip": item["ip"],
            "did": item["did"],
            "pid": item.get("pid", "p93sfg"),
            "dmn": item.get("dmn", "Smart Switch"),
            "dpid": item.get("dpid", [1]),
            CONF_DEVICE_TYPE_CODE: SWITCH_TYPE_CODE,
        }
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=import_data,
            )
        )


class CozyLifeSwitch(SwitchEntity):
    _tcp_client = None
    _attr_is_on = True

    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize."""
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = getattr(tcp_client, 'name', None) or tcp_client.device_id[-4:]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            name=self._tcp_client._device_model_name,
            manufacturer="CozyLife",
            model=self._tcp_client._pid,
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    async def async_update(self):
        await self.hass.async_add_executor_job(self._refresh_state)

    def _refresh_state(self):
        self._state = self._tcp_client.query()
        if self._state:
            self._attr_is_on = 0 < self._state['1']

    @property
    def name(self) -> str:
        return 'cozylife:' + self._name

    @property
    def available(self) -> bool:
        """Return if the device is available."""
        if self._tcp_client._connect:
            return True
        else:
            return False

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._attr_is_on = True

        await self.hass.async_add_executor_job(self._tcp_client.control, {
            '1': 1
        })

        return None

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._attr_is_on = False

        await self.hass.async_add_executor_job(self._tcp_client.control, {
            '1': 0
        })

        return None
