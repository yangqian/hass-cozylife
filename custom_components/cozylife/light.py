"""Platform for sensor integration."""
from __future__ import annotations
from homeassistant.components import zeroconf
import logging
from .tcp_client import tcp_client
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.util import color as colorutil
from homeassistant.components.light import (
    PLATFORM_SCHEMA,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_HS_COLOR,
    ATTR_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODE_ONOFF,
    COLOR_MODE_RGB,
    COLOR_MODE_UNKNOWN,
    FLASH_LONG,
    FLASH_SHORT,
    SUPPORT_EFFECT,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
    LightEntity,
)
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

from homeassistant.helpers.event import async_track_time_interval

import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

LIGHT_SCHEMA = vol.Schema({
    vol.Required('ip'): cv.string,
    vol.Required('did'): cv.string,
    vol.Optional('dmn', default='Smart Bulb Light'): cv.string,
    vol.Optional('pid', default='p93sfg'): cv.string,
    vol.Optional('dpid', default=[1, 2, 3, 4, 5, 7, 8, 9, 13, 14]):
        vol.All(cv.ensure_list, [int])
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('lights', default=[]):
        vol.All(cv.ensure_list, [LIGHT_SCHEMA])
})


SCAN_INTERVAL = timedelta(seconds=240)


CIRCADIAN_BRIGHTNESS = True
try:
  # I am using circadian lighting v1
  from custom_components.circadian_lighting import CIRCADIAN_LIGHTING_UPDATE_TOPIC, DATA_CIRCADIAN_LIGHTING
except:
  CIRCADIAN_BRIGHTNESS = False

_LOGGER = logging.getLogger(__name__)
_LOGGER.info(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    # We only want this platform to be set up via discovery.
    _LOGGER.info(
        f'setup_platform.hass={hass},config={config},async_add_entities={async_add_devices},discovery_info={discovery_info}')
    # zc = await zeroconf.async_get_instance(hass)
    # _LOGGER.info(f'zc={zc}')
    #_LOGGER.info(f'hass.data={hass.data[DOMAIN]}')
    #_LOGGER.info(f'discovery_info={discovery_info}')
    #if discovery_info is None:
    #    return

    lights = []
    for item in config.get('lights'):
        client = tcp_client(item.get('ip'))
        client._device_id = item.get('did')
        client._pid = item.get('pid')
        client._dpid = item.get('dpid')
        client._device_model_name = item.get('dmn')
        lights.append(CozyLifeLight(client, hass))

    async_add_devices(lights)
    for light in lights:
        await hass.async_add_executor_job(light._tcp_client._initSocket)
        await asyncio.sleep(0.01)

    async def async_update(now=None):
        for light in lights:
            await hass.async_add_executor_job(light._refresh_state)
            await asyncio.sleep(0.01)
    async_track_time_interval(hass, async_update, SCAN_INTERVAL)


class CozyLifeLight(LightEntity):
    # _attr_brightness: int | None = None
    # _attr_color_mode: str | None = None
    # _attr_color_temp: int | None = None
    # _attr_hs_color = None
    _tcp_client = None

    _attr_supported_color_modes = {
        COLOR_MODE_HS, COLOR_MODE_COLOR_TEMP, COLOR_MODE_BRIGHTNESS, COLOR_MODE_ONOFF}
    _attr_color_mode = COLOR_MODE_BRIGHTNESS

    _unique_id = ''
    _attr_is_on = False
    _name = ''
    _attr_brightness = 0
    _attr_color_temp = 153
    _attr_hs_color = (0, 0)

    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id

        #circardianlighting initialize
        self._cl = None
        self._max_brightness = 255
        self._min_brightness = 1
        #self._name = tcp_client.device_model_name
        _LOGGER.info(f'before:{self._unique_id}._attr_color_mode={self._attr_color_mode}._attr_supported_color_modes='
                     f'{self._attr_supported_color_modes}.dpid={tcp_client.dpid}')
        self._name = tcp_client.device_id[-4:]
        self._min_mireds = colorutil.color_temperature_kelvin_to_mired(6500)
        self._max_mireds = colorutil.color_temperature_kelvin_to_mired(2700)
        self._miredsratio = (self._max_mireds - self._min_mireds)/1000

        # h s
        if 3 in tcp_client.dpid:
            self._attr_color_mode = COLOR_MODE_COLOR_TEMP
            self._attr_supported_color_modes.add(COLOR_MODE_COLOR_TEMP)

        if 5 in tcp_client.dpid or 6 in tcp_client.dpid:
            self._attr_color_mode = COLOR_MODE_HS
            self._attr_supported_color_modes.add(COLOR_MODE_HS)

        _LOGGER.info(f'after:{self._unique_id}._attr_color_mode={self._attr_color_mode}._attr_supported_color_modes='
                     f'{self._attr_supported_color_modes}.dpid={tcp_client.dpid}')

        self._refresh_state()

    async def async_update(self):
        await self.hass.async_add_executor_job(self._refresh_state)

    def _refresh_state(self):
        """
        query device & set attr
        :return:
        """
        self._state = self._tcp_client.query()
        _LOGGER.info(f'_name={self._name},_state={self._state}')
        if self._state:
            self._attr_is_on = 0 < self._state['1']

        #warning: 3:65535 is detected for HS mode, order here matters
        #warning: 5:65535 for color temp mode, order here matters
        if '3' in self._state:
            #self._attr_color_mode = COLOR_MODE_COLOR_TEMP
            color_temp = self._state['3']
            if color_temp < 60000:
                self._attr_color_mode = COLOR_MODE_COLOR_TEMP
                self._attr_color_temp = int(
                    self._max_mireds-self._state['3'] * self._miredsratio)

        if '4' in self._state:
            self._attr_brightness = int(self._state['4'] / 1000 * 255)

        if '5' in self._state:
            color = self._state['5']
            if color < 60000:
                self._attr_color_mode = COLOR_MODE_HS
                r, g, b = colorutil.color_hs_to_RGB(
                    int(self._state['5']), int(self._state['6'] / 10))
                hs_color = colorutil.color_RGB_to_hs(r*0.80, g, b)
                self._attr_hs_color = hs_color

    #autobrightness from circadian_lighting if enabled
    def calc_brightness(self):
        if self._cl == None:
          self._cl = self.hass.data.get(DATA_CIRCADIAN_LIGHTING)
          if self._cl == None:
            return self.brightness
        if self._cl.data['percent'] > 0:
            return self._max_brightness
        else:
            return int(((self._max_brightness - self._min_brightness) * ((100+self._cl.data['percent']) / 100)) + self._min_brightness)

    @property
    def name(self) -> str:
        return 'cozylife:' + self._name

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        # self._refresh_state()
        return self._attr_is_on

    @property
    def color_temp(self) -> int | None:
        """Return the CT color value in mireds."""
        return self._attr_color_temp

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._attr_is_on = True

        # 1-255
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        # 153 ~ 370
        colortemp = kwargs.get(ATTR_COLOR_TEMP)

        # tuple
        hs_color = kwargs.get(ATTR_HS_COLOR)

        rgb = kwargs.get(ATTR_RGB_COLOR)
        flash = kwargs.get(ATTR_FLASH)
        effect = kwargs.get(ATTR_EFFECT)
        _LOGGER.info(
            f'turn_on.kwargs={kwargs},colortemp={colortemp},hs_color={hs_color}')

        payload = {'1': 255, '2': 0}
        count = 0
        if brightness is not None:
            # Color: mininum light brightness 12, max 1000
            # White mininum light brightness 4, max 1000
            payload['4'] = int(brightness / 255 * 1000)
            self._attr_brightness = brightness
            count += 1

        if colortemp is not None:
            # 0-694
            self._attr_color_mode = COLOR_MODE_COLOR_TEMP
            #payload['3'] = 1000 - colortemp * 2
            #self._attr_color_temp = int(self._max_mireds-self._state['3'] * self._miredsratio)
            payload['3'] = 1000 - \
                int((colortemp - self._min_mireds) / self._miredsratio)
            count += 1

        if hs_color is not None:
            # 0-360
            # 0-1000
            self._attr_color_mode = COLOR_MODE_HS
            self._attr_hs_color = hs_color
            r, g, b = colorutil.color_hs_to_RGB(*hs_color)
            # color is not balanced right. needs additional tuning
            hs_color = colorutil.color_RGB_to_hs(r, g, b)
            payload['5'] = int(hs_color[0])
            payload['6'] = int(hs_color[1] * 10)
            count += 1

        if count == 0:
            #autocolortemp when brightness color temp and hs_color is not set
            if CIRCADIAN_BRIGHTNESS:
                brightness = self.calc_brightness()
                payload['4'] = int(brightness / 255 * 1000)
                self._attr_brightness = brightness
                self._attr_color_mode = COLOR_MODE_COLOR_TEMP
                colortemp_in_kelvin = self._cl.data['colortemp']
                colortemp = colorutil.color_temperature_kelvin_to_mired(
                    colortemp_in_kelvin)
                payload['3'] = 1000 - \
                    int((colortemp - self._min_mireds) / self._miredsratio)
                _LOGGER.info(f'color={colortemp},payload3={payload["3"]}')

        await self.hass.async_add_executor_job(self._tcp_client.control, payload)
        # self._refresh_state()
        return None

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._attr_is_on = False
        _LOGGER.info(f'turn_off.kwargs={kwargs}')
        payload = {'1': 0}
        await self.hass.async_add_executor_job(self._tcp_client.control, payload)
        # self._refresh_state()

        return None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value [float, float]."""
        #_LOGGER.info('hs_color')
        # self._refresh_state()
        return self._attr_hs_color

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        #_LOGGER.info('brightness')
        # self._refresh_state()
        return self._attr_brightness

    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        #_LOGGER.info('color_mode')
        return self._attr_color_mode

    @property
    def available(self):
        """Return True if device is available."""
        #return True
        if self._tcp_client._connect:
            return True
        else:
            return False

    @property
    def min_mireds(self):
        """Return color temperature min mireds."""
        return self._min_mireds

    @property
    def max_mireds(self):
        """Return color temperature max mireds."""
        return self._max_mireds

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    @property
    def assumed_state(self):
        return True
