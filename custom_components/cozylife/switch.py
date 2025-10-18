"""Switch platform for CozyLife devices."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_AREA, DOMAIN, MANUFACTURER
from .helpers import normalize_area_value, resolve_area_id
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
    switches: list[CozyLifeSwitch] = []

    timeout = data.get("timeout", entry.data.get("timeout", 0.3))

    if device := data.get("device"):
        if device.get("type") == "switch":
            client = tcp_client(device.get("ip"), timeout=timeout)
            client._device_id = device.get("did")
            client._pid = device.get("pid")
            client._dpid = device.get("dpid")
            client._device_model_name = device.get("dmn")
            fallback_name = client._device_model_name or (
                client.device_id[-4:] if client.device_id else "CozyLife"
            )
            friendly_name = (
                data.get(CONF_NAME)
                or data.get("name")
                or fallback_name
            )
            raw_area = data.get(CONF_AREA) or data.get("location")
            area_id = resolve_area_id(hass, raw_area) or normalize_area_value(raw_area)
            client.name = friendly_name
            switches.append(
                CozyLifeSwitch(
                    client,
                    hass,
                    name=friendly_name,
                    area_id=area_id,
                )
            )
    else:
        devices = data.get("devices", {})
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

    def __init__(
        self,
        tcp_client: tcp_client,
        hass,
        *,
        name: str | None = None,
        area_id: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = name or tcp_client.name or tcp_client.device_id[-4:]
        self._area_id = area_id or None
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, tcp_client.device_id)},
            manufacturer=MANUFACTURER,
            model=tcp_client._device_model_name,
            name=self._name,
        )
        self._device_info["name"] = self._name
        if self._area_id:
            self._device_info["suggested_area"] = self._area_id
        self._attr_name = self._name
        self._attr_suggested_area = None
        self._refresh_state()

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._area_id:
            area_registry = ar.async_get(self.hass)
            area = area_registry.async_get_area(self._area_id)
            suggested_area = area.name if area else self._area_id
            self._device_info["suggested_area"] = suggested_area
            self._attr_suggested_area = suggested_area
        
    async def async_update(self):
        await self.hass.async_add_executor_job(self._refresh_state)

    def _refresh_state(self):
        self._state = self._tcp_client.query()
        _LOGGER.info(f'_name={self._name},_state={self._state}')
        if self._state:
            self._attr_is_on = 0 < self._state['1']
    
    @property
    def name(self) -> str:
        return self._name

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info
    
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
