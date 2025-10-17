"""Switch platform for CozyLife devices."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .tcp_client import tcp_client

SCAN_INTERVAL = timedelta(seconds=240)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CozyLife switches from a config entry."""

    data = hass.data[DOMAIN][entry.entry_id]
    devices = data["devices"]
    switches: list[CozyLifeSwitch] = []

    timeout = entry.data["timeout"]

    for item in devices.get("switches", []):
        client = tcp_client(item.get("ip"), timeout=timeout)
        client._device_id = item.get("did")
        client._pid = item.get("pid")
        client._dpid = item.get("dpid")
        client.name = item.get("name")
        client._device_model_name = item.get("dmn")
        switches.append(CozyLifeSwitch(client, hass))

    if not switches:
        return

    async_add_entities(switches)

    for switch in switches:
        await hass.async_add_executor_job(switch._tcp_client._initSocket)
        await asyncio.sleep(0.01)

    async def async_update(now=None):
        for switch in switches:
            await hass.async_add_executor_job(switch._refresh_state)
            await asyncio.sleep(0.01)

    remove_update = async_track_time_interval(hass, async_update, SCAN_INTERVAL)

    data.setdefault("switch_runtime", {})
    data["switch_runtime"].update(
        {
            "switches": switches,
            "remove_update": remove_update,
        }
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload CozyLife switch entities for a config entry."""

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    runtime = data.get("switch_runtime", {})

    if remove := runtime.get("remove_update"):
        remove()

    return True


class CozyLifeSwitch(SwitchEntity):
    _tcp_client = None
    _attr_is_on = True
    
    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.name or tcp_client.device_id[-4:]
        self._refresh_state()

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id
        
    async def async_update(self):
        await self.hass.async_add_executor_job(self._refresh_state)

    def _refresh_state(self):
        self._state = self._tcp_client.query()
        _LOGGER.info(f'_name={self._name},_state={self._state}')
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

        _LOGGER.info(f'turn_on:{kwargs}')

        await self.hass.async_add_executor_job(self._tcp_client.control, {
            '1': 1
        })

        return None
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._attr_is_on = False

        _LOGGER.info('turn_off')

        await self.hass.async_add_executor_job(self._tcp_client.control, {
            '1': 0
        })
        
        return None
