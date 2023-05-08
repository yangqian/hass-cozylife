"""Platform for sensor integration."""
from __future__ import annotations
from homeassistant.components import zeroconf
import logging
from .tcp_client import tcp_client
from datetime import timedelta
import time

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
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
from homeassistant.const import TEMP_CELSIUS, CONF_EFFECT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform
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
SWITCH_SCAN_INTERVAL = timedelta(seconds=20)


CIRCADIAN_BRIGHTNESS = True
try:
  import custom_components.circadian_lighting as cir
  DATA_CIRCADIAN_LIGHTING=cir.DOMAIN #'circadian_lighting'
except:
  CIRCADIAN_BRIGHTNESS = False

_LOGGER = logging.getLogger(__name__)
_LOGGER.info(__name__)

SERVICE_SET_EFFECT = "set_effect"
SERVICE_SET_ALL_EFFECT = "set_all_effect"
scenes = ['manual','natural','sleep','warm','study','chrismas']
SERVICE_SCHEMA_SET_ALL_EFFECT = {
vol.Required(CONF_EFFECT): vol.In([mode.lower() for mode in scenes])
}
SERVICE_SCHEMA_SET_EFFECT = {
vol.Required(CONF_EFFECT): vol.In([mode.lower() for mode in scenes])
}

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
    # treat switch as light in home assistant
    switches = []
    for item in config.get('lights'):
        client = tcp_client(item.get('ip'))
        client._device_id = item.get('did')
        client._pid = item.get('pid')
        client._dpid = item.get('dpid')
        client._device_model_name = item.get('dmn')
        if 'switch' not in client._device_model_name.lower():
          lights.append(CozyLifeLight(client, hass, scenes))
        else:
          switches.append(CozyLifeSwitchAsLight(client, hass))

    async_add_devices(lights)
    for light in lights:
        await hass.async_add_executor_job(light._tcp_client._initSocket)
        await asyncio.sleep(0.01)

    async def async_update(now=None):
        for light in lights:
            if light._attr_is_on and light._effect ==  'natural':
              await light.async_turn_on(effect='natural')
            else:
              await hass.async_add_executor_job(light._refresh_state)
            await asyncio.sleep(0.01)
    async_track_time_interval(hass, async_update, SCAN_INTERVAL)

    async_add_devices(switches)
    for light in switches:
        await hass.async_add_executor_job(light._tcp_client._initSocket)
        await asyncio.sleep(0.01)

    async def async_update(now=None):
        for light in switches:
            await hass.async_add_executor_job(light._refresh_state)
            await asyncio.sleep(0.01)
    async_track_time_interval(hass, async_update, SWITCH_SCAN_INTERVAL)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_EFFECT, SERVICE_SCHEMA_SET_EFFECT, "async_set_effect"
    )
    async def async_set_all_effect(call:ServiceCall):
        for light in lights:
            await light.async_set_effect(call.data.get(ATTR_EFFECT))
            await asyncio.sleep(0.01)
    hass.services.async_register(DOMAIN, SERVICE_SET_ALL_EFFECT, async_set_all_effect)





class CozyLifeSwitchAsLight(LightEntity):
    _tcp_client = None
    _attr_is_on = True
    
    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.device_id[-4:]
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


class CozyLifeLight(CozyLifeSwitchAsLight,RestoreEntity):
    # _attr_brightness: int | None = None
    # _attr_color_mode: str | None = None
    # _attr_color_temp: int | None = None
    # _attr_hs_color = None
    _tcp_client = None

    _attr_supported_color_modes = {
        COLOR_MODE_ONOFF}
    _attr_color_mode = COLOR_MODE_BRIGHTNESS

    _unique_id = ''
    _attr_is_on = False
    _name = ''
    _attr_brightness = 0
    _attr_color_temp = 153
    _attr_hs_color = (0, 0)
    _transitioning = 0

    def __init__(self, tcp_client: tcp_client, hass, scenes) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._scenes = scenes
        self._effect = 'manual'
        #self._lasteffect = 'manual'

        #circardianlighting initialize
        self._cl = None
        self._max_brightness = 255
        self._min_brightness = 1
        #self._name = tcp_client._device_model_name
        _LOGGER.info(f'before:{self._unique_id}._attr_color_mode={self._attr_color_mode}._attr_supported_color_modes='
                     f'{self._attr_supported_color_modes}.dpid={tcp_client.dpid}')
        self._name = tcp_client.device_id[-4:]
        self._min_mireds = colorutil.color_temperature_kelvin_to_mired(6500)
        self._max_mireds = colorutil.color_temperature_kelvin_to_mired(2700)
        self._miredsratio = (self._max_mireds - self._min_mireds)/1000

        # h s
        if not 'switch' in self._tcp_client._device_model_name.lower():

            if 3 in tcp_client.dpid:
                self._attr_color_mode = COLOR_MODE_COLOR_TEMP
                self._attr_supported_color_modes.add(COLOR_MODE_COLOR_TEMP)

            if 4 in tcp_client.dpid:
                self._attr_supported_color_modes.add(COLOR_MODE_BRIGHTNESS)

            if 5 in tcp_client.dpid or 6 in tcp_client.dpid:
                self._attr_color_mode = COLOR_MODE_HS
                self._attr_supported_color_modes.add(COLOR_MODE_HS)

        _LOGGER.info(f'after:{self._unique_id}._attr_color_mode={self._attr_color_mode}._attr_supported_color_modes='
                     f'{self._attr_supported_color_modes}.dpid={tcp_client.dpid}')


        self._refresh_state()
        self.SUPPORT_COZYLIGHT = self.get_supported_features()

    async def async_set_effect(self, effect: str):
        """Set the effect regardless it is On or Off."""
        _LOGGER.info(f'onoff:{self._attr_is_on} effect:{effect}')
        self._effect = effect
        if self._attr_is_on:
            await self.async_turn_on(effect=effect)
          

    @property
    def effect(self):
        """Return the current effect."""
        return self._effect

    @property
    def effect_list(self):
        """Return the list of supported effects.
        """
        return self._scenes

    def _refresh_state(self):
        """
        query device & set attr
        :return:
        """
        self._state = self._tcp_client.query()
        _LOGGER.info(f'_name={self._name},_state={self._state}')
        if self._state:
            self._attr_is_on = 0 < self._state['1']

            if '2' in self._state:
                if self._state['2'] == 0:
                    if '3' in self._state:
                        #self._attr_color_mode = COLOR_MODE_COLOR_TEMP
                        color_temp = self._state['3']
                        if color_temp < 60000:
                            self._attr_color_mode = COLOR_MODE_COLOR_TEMP
                            self._attr_color_temp = round(
                                self._max_mireds-self._state['3'] * self._miredsratio)

                    if '4' in self._state:
                        self._attr_brightness = int(self._state['4'] / 1000 * 255)

                    if '5' in self._state:
                        color = self._state['5']
                        if color < 60000:
                            self._attr_color_mode = COLOR_MODE_HS
                            r, g, b = colorutil.color_hs_to_RGB(
                                round(self._state['5']), round(self._state['6'] / 10))
                            ## May need to adjust
                            hs_color = colorutil.color_RGB_to_hs(r, g, b)
                            self._attr_hs_color = hs_color

    #autobrightness from circadian_lighting if enabled
    def calc_color_temp(self):
        if self._cl == None:
          self._cl = self.hass.data.get(DATA_CIRCADIAN_LIGHTING)
          if self._cl == None:
            return None
        colortemp_in_kelvin = self._cl._colortemp
        autocolortemp = colorutil.color_temperature_kelvin_to_mired(
            colortemp_in_kelvin)
        return autocolortemp
    def calc_brightness(self):
        if self._cl == None:
          self._cl = self.hass.data.get(DATA_CIRCADIAN_LIGHTING)
          if self._cl == None:
            return None
        if self._cl._percent > 0:
            return self._max_brightness
        else:
            return round(((self._max_brightness - self._min_brightness) * ((100+self._cl._percent) / 100)) + self._min_brightness)


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

        transition = kwargs.get(ATTR_TRANSITION)

            

        # rgb = kwargs.get(ATTR_RGB_COLOR)
        #flash = kwargs.get(ATTR_FLASH)
        effect = kwargs.get(ATTR_EFFECT)
        _LOGGER.info(
            f'turn_on.kwargs={kwargs},colortemp={colortemp},hs_color={hs_color}')
        originalbrightness = 0
        originalcolortemp = self._attr_color_temp
        originalhs= self._attr_hs_color

        if self._attr_is_on:
          originalbrightness = self._attr_brightness

        payload = {'1': 255, '2': 0}
        count = 0
        if brightness is not None:
            # Color: mininum light brightness 12, max 1000
            # White mininum light brightness 4, max 1000
            self._effect = 'manual'
            payload['4'] = round(brightness / 255 * 1000)
            self._attr_brightness = brightness
            count += 1

        if colortemp is not None:
            # 0-694
            #payload['3'] = 1000 - colortemp * 2
            self._effect = 'manual'
            self._attr_color_mode = COLOR_MODE_COLOR_TEMP
            self._attr_color_temp = colortemp
            payload['3'] = 1000 - \
                round((colortemp - self._min_mireds) / self._miredsratio)
            count += 1

        if hs_color is not None:
            # 0-360
            # 0-1000
            self._effect = 'manual'
            self._attr_color_mode = COLOR_MODE_HS
            self._attr_hs_color = hs_color
            r, g, b = colorutil.color_hs_to_RGB(*hs_color)
            # color is not balanced right. needs additional tuning
            hs_color = colorutil.color_RGB_to_hs(r, g, b)
            payload['5'] = round(hs_color[0])
            payload['6'] = round(hs_color[1] * 10)
            count += 1

        if count == 0:
            #autocolortemp when brightness color temp and hs_color is not set
            if effect is not None: 
                self._effect = effect
            if self._effect == 'natural':
                if CIRCADIAN_BRIGHTNESS:
                    brightness = self.calc_brightness()
                    payload['4'] = round(brightness / 255 * 1000)
                    self._attr_brightness = brightness
                    self._attr_color_mode = COLOR_MODE_COLOR_TEMP
                    colortemp = self.calc_color_temp()
                    payload['3'] = 1000 - \
                        round((colortemp - self._min_mireds) / self._miredsratio)
                    _LOGGER.info(f'color={colortemp},payload3={payload["3"]}')
            elif self._effect == 'sleep':
                    #payload['4'] = 4
                    #payload['3'] = 0
                    #payload['4'] = 12
                    brightness = 5
                    self._attr_brightness = brightness
                    payload['4'] = round(brightness / 255 * 1000)
                    self._attr_color_mode = COLOR_MODE_HS
                    self._attr_hs_color = (16,100)
                    payload['5'] = round(16)
                    payload['6'] = round(1000)
            elif self._effect == 'study':
                    payload['4'] = 1000
                    payload['3'] = 1000
            elif self._effect == 'warm':
                    payload['4'] = 1000
                    payload['3'] = 0
            elif self._effect == 'chrismas':
                    payload['2'] = 1
                    payload['4'] = 1000
                    payload['8'] = 500
                    payload['7'] = '03000003E8FFFF007803E8FFFF00F003E8FFFF003C03E8FFFF00B403E8FFFF010E03E8FFFF002603E8FFFF'

        self._transitioning = 0

        if transition: 
            self._transitioning = time.time()
            now = self._transitioning
            if self._effect =='chrismas':
                await self.hass.async_add_executor_job(self._tcp_client.control, payload)
                return None
            if brightness:
                payloadtemp = {'1': 255, '2': 0}
                p4i = round(originalbrightness / 255 * 1000)
                p4f = payload['4']
                p4steps = abs(round((p4i-p4f)/4))
            else:
                p4steps = 0
            if self._attr_color_mode == COLOR_MODE_COLOR_TEMP:
                p3i = 1000 - round((originalcolortemp - self._min_mireds) / self._miredsratio)
                p3steps = 0
                if '3' in payload:
                    p3f = payload['3']
                    p3steps = abs(round((p3i-p3f)/4))
                steps = p3steps if p3steps > p4steps else p4steps
                if steps <= 0: 
                    return None
                stepseconds = transition / steps
                if stepseconds < 0.3:
                    steps = round(transition / stepseconds)
                    stepseconds = transition / steps
                _LOGGER.info(f'steps={steps}')
                for s in range(steps):
                    payloadtemp['4']= round(p4i + (p4f - p4i) * s / steps)
                    if p3steps != 0:
                        payloadtemp['3']= round(p3i + (p3f - p3i) * s / steps)
                    if now == self._transitioning:
                        await self.hass.async_add_executor_job(self._tcp_client.control, payloadtemp)
                        await asyncio.sleep(stepseconds)
                    else:
                        return None
            elif  self._attr_color_mode == COLOR_MODE_HS:
                p5i = originalhs[0]
                p6i = originalhs[1]*10
                p5steps = 0
                p6steps = 0
                if '5' in payload:
                    p5f = payload['5']
                    p6f = payload['6']
                    p5steps = abs(round((p5i - p5f) / 3))
                    p6steps = abs(round((p6i - p6f) / 10))
                steps = max([p4steps, p5steps, p6steps])
                if steps <= 0: 
                    return None
                stepseconds = transition / steps
                if stepseconds < 4:
                    steps = round(transition / stepseconds)
                    stepseconds = transition / steps
                _LOGGER.info(f'steps={steps}')
                for s in range(steps):
                    payloadtemp['4']= round(p4i + (p4f - p4i) * s / steps)
                    if p5steps != 0: 
                        payloadtemp['5']= round(p5i + (p5f - p5i) * s / steps)
                        payloadtemp['6']= round(p6i + (p6f - p6i) * s / steps)
                    if now == self._transitioning:
                        await self.hass.async_add_executor_job(self._tcp_client.control, payloadtemp)
                        await asyncio.sleep(stepseconds)
                    else:
                        return None
        else:
            await self.hass.async_add_executor_job(self._tcp_client.control, payload)
        # self._refresh_state()
        return None

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._transitioning = 0
        await super().async_turn_off(*kwargs)
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
    def min_mireds(self):
        """Return color temperature min mireds."""
        return self._min_mireds

    @property
    def max_mireds(self):
        """Return color temperature max mireds."""
        return self._max_mireds


    @property
    def assumed_state(self):
        return True

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if not last_state:
            return
        if 'last_effect' in last_state.attributes:
            self._effect = last_state.attributes['last_effect']

    @property
    def extra_state_attributes(self):
        attributes = {}
        attributes['last_effect'] = self._effect
        attributes['transitioning'] = self._transitioning

        return attributes

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return self.SUPPORT_COZYLIGHT

    def get_supported_features(self) -> int:
        """Flag supported features."""
        features = 0
        features = features | SUPPORT_EFFECT | SUPPORT_TRANSITION
        try:
            # Map features for better reading
            if COLOR_MODE_BRIGHTNESS in self._attr_supported_color_modes:
                features = features | SUPPORT_BRIGHTNESS
            if COLOR_MODE_HS in self._attr_supported_color_modes:
                features = features | SUPPORT_COLOR
            if COLOR_MODE_COLOR_TEMP in self._attr_supported_color_modes:
                features = features | SUPPORT_COLOR_TEMP
        except:
            pass
        # fallback
        return features