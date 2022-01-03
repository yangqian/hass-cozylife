"""Platform for sensor integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import TEMP_CELSIUS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing import Any, Final, Literal, TypedDict, final
from .const import (
    DOMAIN,
    SWITCH_TYPE_CODE,
    LIGHT_TYPE_CODE,
    LIGHT_DPID,
    SWITCH,
    WORK_MODE,
    TEMP,
    BRIGHT,
    HUE,
    SAT,
)
import logging

_LOGGER = logging.getLogger(__name__)
_LOGGER.info('switch')

SCAN_INTERVAL = timedelta(seconds=240)

async def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    # We only want this platform to be set up via discovery.
    # logging.info('setup_platform', hass, config, add_entities, discovery_info)
    _LOGGER.info('setup_platform')
    
    if discovery_info is None:
        return


    switches = []
    for item in config.get('switches'):
        client = tcp_client(item.get('ip'))
        client._device_id = item.get('did')
        client._pid = item.get('pid')
        client._dpid = item.get('dpid')
        client._device_model_name = item.get('dmn')
        switches.append(CozyLifeSwitch(client))

    async_add_entities(switches)
    for switch in switches:
        await hass.async_add_executor_job(switch._tcp_client._initSocket)
        await asyncio.sleep(0.01)

    async def async_update(now=None):
        for switch in switches:
            await hass.async_add_executor_job(switch._refresh_state)
            await asyncio.sleep(0.01)

    async_track_time_interval(hass, async_update, SCAN_INTERVAL)


class CozyLifeSwitch(SwitchEntity):
    _tcp_client = None
    _attr_is_on = True
    
    def __init__(self, tcp_client) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.device_model_name
        self._refresh_state()
    
    def _refresh_state(self):
        self._state = self._tcp_client.query()
        self._attr_is_on = 0 != self._state['1']
    
    @property
    def name(self) -> str:
        return 'cozylife:' + self._name
    
    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return True
    
    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        self._attr_is_on = True

        self._refresh_state()
        return self._attr_is_on
    
    def turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._attr_is_on = True
        _LOGGER.info(f'turn_on:{kwargs}')
        self._tcp_client.control({'1': 255})
        return None
        raise NotImplementedError()
    
    def turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._attr_is_on = False
        _LOGGER.info('turn_off')
        self._tcp_client.control({'1': 0})
        return None
        
        raise NotImplementedError()
