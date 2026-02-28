"""Platform for CozyLife light integration."""
from __future__ import annotations
import logging
from .tcp_client import tcp_client
from datetime import timedelta
import time

from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import color as colorutil
from homeassistant.components.light import (
    PLATFORM_SCHEMA,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    LightEntityFeature,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EFFECT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing import Any
from .const import (
    DOMAIN,
    SWITCH_TYPE_CODE,
    LIGHT_TYPE_CODE,
    CONF_DEVICE_TYPE_CODE,
    LIGHT_DPID,
    SWITCH,
    WORK_MODE,
    TEMP,
    BRIGHT,
    HUE,
    SAT,
    DEFAULT_MIN_KELVIN,
    DEFAULT_MAX_KELVIN,
)

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


SCAN_INTERVAL = timedelta(seconds=60)
MIN_INTERVAL=0.2

CIRCADIAN_BRIGHTNESS = True
try:
  import custom_components.circadian_lighting as cir
  DATA_CIRCADIAN_LIGHTING=cir.DOMAIN #'circadian_lighting'
except:
  CIRCADIAN_BRIGHTNESS = False

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_EFFECT = "set_effect"
scenes = ['manual','natural','sleep','warm','study','chrismas']
SERVICE_SCHEMA_SET_EFFECT = {
vol.Required(CONF_EFFECT): vol.In([mode.lower() for mode in scenes])
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CozyLife light from a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    data = entry.data

    if 'switch' not in data.get("dmn", "").lower():
        entity = CozyLifeLight(client, hass, scenes)
    else:
        entity = CozyLifeSwitchAsLight(client, hass)

    async_add_entities([entity])

    # Register light entities for set_all_effect service
    if isinstance(entity, CozyLifeLight):
        hass.data[DOMAIN].setdefault("light_entities", [])
        hass.data[DOMAIN]["light_entities"].append(entity)

    # Register entity-level set_effect service (idempotent per platform)
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_EFFECT, SERVICE_SCHEMA_SET_EFFECT, "async_set_effect"
    )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Import YAML configuration as config entries."""
    _LOGGER.warning(
        "Configuration of CozyLife lights via YAML is deprecated. "
        "Your YAML config has been imported. Please remove it."
    )
    for item in config.get('lights', []):
        # Determine device type: switches exposed as lights get type "01" (light platform)
        device_type = LIGHT_TYPE_CODE
        if 'switch' in item.get('dmn', '').lower():
            device_type = LIGHT_TYPE_CODE  # stays on light platform even if switch-like

        import_data = {
            "ip": item["ip"],
            "did": item["did"],
            "pid": item.get("pid", "p93sfg"),
            "dmn": item.get("dmn", "Smart Bulb Light"),
            "dpid": item.get("dpid", [1, 2, 3, 4, 5, 7, 8, 9, 13, 14]),
            CONF_DEVICE_TYPE_CODE: device_type,
        }
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=import_data,
            )
        )


class CozyLifeSwitchAsLight(LightEntity):

    _tcp_client = None
    _attr_is_on = True
    _attr_color_mode = ColorMode.ONOFF
    _unrecorded_attributes = frozenset({"brightness","color_temp_kelvin"})

    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.device_id[-4:]
        self._attr_supported_color_modes = {ColorMode.ONOFF}

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
    _attr_brightness: int | None = None
    _attr_color_mode: ColorMode | None = None
    _attr_color_temp_kelvin: int | None = None
    _attr_hs_color = None
    _unrecorded_attributes = frozenset({"brightness","color_temp_kelvin"})

    _tcp_client = None

    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, tcp_client: tcp_client, hass, scenes) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self.hass = hass
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._scenes = scenes
        self._effect = 'manual'

        #circardianlighting initialize
        self._cl = None
        self._max_brightness = 255
        self._min_brightness = 1
        _LOGGER.info(f'before:{self._unique_id}._attr_color_mode={self._attr_color_mode}._attr_supported_color_modes='
                     f'{self._attr_supported_color_modes}.dpid={tcp_client.dpid}')
        self._name = tcp_client.device_id[-4:]
        # Report kelvin bounds to Home Assistant (min = warmest, max = coldest)
        self._attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
        self._attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN

        # Device protocol uses 0-1000 scale mapping linearly to kelvin
        # 0 = warmest (min_kelvin), 1000 = coldest (max_kelvin)
        self._kelvin_ratio = (self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin) / 1000
        self._attr_color_temp_kelvin = self._attr_max_color_temp_kelvin
        self._attr_hs_color = (0, 0)
        self._transitioning = 0
        self._attr_is_on = False
        self._attr_brightness = 0

        # Per-instance copy to avoid mutating class-level set
        self._attr_supported_color_modes = {ColorMode.ONOFF}

        # h s
        if not 'switch' in self._tcp_client._device_model_name.lower():

            if 3 in tcp_client.dpid:
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)


            if 4 in tcp_client.dpid:
                self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)

            if 5 in tcp_client.dpid or 6 in tcp_client.dpid:
                self._attr_color_mode = ColorMode.HS
                self._attr_supported_color_modes.add(ColorMode.HS)

        _LOGGER.info(f'after:{self._unique_id}._attr_color_mode={self._attr_color_mode}._attr_supported_color_modes='
                     f'{self._attr_supported_color_modes}.dpid={tcp_client.dpid}')

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
                        color_temp = self._state['3']
                        if color_temp < 60000:
                            self._attr_color_mode = ColorMode.COLOR_TEMP
                            self._attr_color_temp_kelvin = round(
                                self._attr_min_color_temp_kelvin + self._state['3'] * self._kelvin_ratio)

                    if '4' in self._state:
                        self._attr_brightness = int(self._state['4'] / 1000 * 255)

                    if '5' in self._state:
                        color = self._state['5']
                        if color < 60000:
                            self._attr_color_mode = ColorMode.HS
                            r, g, b = colorutil.color_hs_to_RGB(
                                round(self._state['5']), round(self._state['6'] / 10))
                            ## May need to adjust
                            hs_color = colorutil.color_RGB_to_hs(r, g, b)
                            self._attr_hs_color = hs_color

    async def async_update(self):
        """Poll device state. Handle natural effect on update cycle."""
        if self._attr_is_on and self._effect == 'natural':
            await self.async_turn_on(effect='natural')
        else:
            await self.hass.async_add_executor_job(self._refresh_state)

    #autobrightness from circadian_lighting if enabled
    def calc_color_temp_kelvin(self):
        if self._cl == None:
          self._cl = self.hass.data.get(DATA_CIRCADIAN_LIGHTING)
          if self._cl == None:
            return None
        return self._cl._colortemp
    def calc_brightness(self):
        if self._cl == None:
          self._cl = self.hass.data.get(DATA_CIRCADIAN_LIGHTING)
          if self._cl == None:
            return None
        if self._cl._percent > 0:
            return self._max_brightness
        else:
            return round(((self._max_brightness - self._min_brightness) * ((100+self._cl._percent) / 100)) + self._min_brightness)


    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""

        # 1-255
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        # kelvin
        colortemp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

        # tuple
        hs_color = kwargs.get(ATTR_HS_COLOR)

        transition = kwargs.get(ATTR_TRANSITION)



        # rgb = kwargs.get(ATTR_RGB_COLOR)
        #flash = kwargs.get(ATTR_FLASH)
        effect = kwargs.get(ATTR_EFFECT)

        originalcolortemp_kelvin = self._attr_color_temp_kelvin
        originalhs = self._attr_hs_color
        if self._attr_is_on:
            originalbrightness = self._attr_brightness
        else:
            originalbrightness = 0
        _LOGGER.info(
            f'turn_on.kwargs={kwargs},colortemp_kelvin={colortemp_kelvin},hs_color={hs_color},originalbrightness={originalbrightness},self._attr_is_on={self._attr_is_on}')
        self._attr_is_on = True
        self.async_write_ha_state()
        payload = {'1': 255, '2': 0}
        count = 0
        if brightness is not None:
            # Color: mininum light brightness 12, max 1000
            # White mininum light brightness 4, max 1000
            self._effect = 'manual'
            payload['4'] = round(brightness / 255 * 1000)
            self._attr_brightness = brightness
            count += 1

        if colortemp_kelvin is not None:
            self._effect = 'manual'
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = colortemp_kelvin
            payload['3'] = round(
                (colortemp_kelvin - self._attr_min_color_temp_kelvin) / self._kelvin_ratio)
            count += 1

        if hs_color is not None:
            # 0-360
            # 0-1000
            self._effect = 'manual'
            self._attr_color_mode = ColorMode.HS
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
                    self._attr_color_mode = ColorMode.COLOR_TEMP
                    colortemp_kelvin = self.calc_color_temp_kelvin()
                    payload['3'] = round(
                        (colortemp_kelvin - self._attr_min_color_temp_kelvin) / self._kelvin_ratio)
                    _LOGGER.info(f'color_kelvin={colortemp_kelvin},payload3={payload["3"]}')
                    if self._transitioning !=0:
                        return None
                    if transition is None:
                        transition=5
            elif self._effect == 'sleep':
                    payload['4'] = 4
                    payload['3'] = 0
                    payload['4'] = 12
                    self._attr_color_mode = ColorMode.COLOR_TEMP
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
                self._transitioning = 0
                return None
            if brightness:
                payloadtemp = {'1': 255, '2': 0}
                p4i = round(originalbrightness / 255 * 1000)
                p4f = payload['4']
                p4steps = abs(round((p4i-p4f)/4))
                _LOGGER.info(f'p4i={p4i},p4f={p4f},p4steps={p4steps}')
            else:
                p4steps = 0
            if self._attr_color_mode == ColorMode.COLOR_TEMP:
                p3i = round((originalcolortemp_kelvin - self._attr_min_color_temp_kelvin) / self._kelvin_ratio)
                p3steps = 0
                if '3' in payload:
                    p3f = payload['3']
                    p3steps = abs(round((p3i-p3f)/4))
                _LOGGER.info(f'p3i={p3i},p3f={p3f},p3steps={p3steps}')
                steps = p3steps if p3steps > p4steps else p4steps
                if steps <= 0:
                    self._transitioning = 0
                    return None
                stepseconds = transition / steps
                if stepseconds < MIN_INTERVAL:
                    stepseconds = MIN_INTERVAL
                    steps = round(transition / stepseconds)
                    stepseconds = transition / steps
                _LOGGER.info(f'steps={steps},transition={transition},stepseconds={stepseconds},p3steps={p3steps},p4steps={p4steps}')
                for s in range(1,steps+1):
                    payloadtemp['4']= round(p4i + (p4f - p4i) * s / steps)
                    if p3steps != 0:
                        payloadtemp['3']= round(p3i + (p3f - p3i) * s / steps)
                    if now == self._transitioning:
                        await self.hass.async_add_executor_job(self._tcp_client.control, payloadtemp)
                        _LOGGER.info(f'payloadtemp={payloadtemp},stepseconds={stepseconds}')
                        if s<steps:
                            await asyncio.sleep(stepseconds)
                    else:
                        self._transitioning = 0
                        return None

            elif  self._attr_color_mode == ColorMode.HS:
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
                    self._transitioning = 0
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
                        self._transitioning = 0
                        return None
        else:
            await self.hass.async_add_executor_job(self._tcp_client.control, payload)
        # self._refresh_state()
        self._transitioning = 0
        return None

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._transitioning = 0
        self._attr_is_on = False
        self.async_write_ha_state()
        transition = kwargs.get(ATTR_TRANSITION)
        originalbrightness=self._attr_brightness
        if self._effect == 'natural' and transition is None:
            transition = 5
        if transition:
            self._transitioning = time.time()
            now = self._transitioning
            payloadtemp = {'1': 255, '2': 0}
            p4i = round(originalbrightness / 255 * 1000)
            p4f = 0
            steps = abs(round((p4i-p4f)/4))
            if steps <= 0:
                self._transitioning = 0
                await super().async_turn_off()
                return None
            stepseconds = transition / steps
            if stepseconds < MIN_INTERVAL:
                stepseconds = MIN_INTERVAL
                steps = round(transition / stepseconds)
                stepseconds = transition / steps
            for s in range(1+steps+1):
                payloadtemp['4']= round(p4i + (p4f - p4i) * s / steps)
                if now == self._transitioning:
                    await self.hass.async_add_executor_job(self._tcp_client.control, payloadtemp)
                    if s<steps:
                        await asyncio.sleep(stepseconds)
                    else:
                        await super().async_turn_off()
                else:
                    return None
        else:
           await super().async_turn_off()
        self._transitioning = 0
        return None


    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value [float, float]."""
        return self._attr_hs_color

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return self._attr_brightness

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the color mode of the light."""
        return self._attr_color_mode


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
    def supported_features(self) -> LightEntityFeature:
        """Flag supported features."""
        return LightEntityFeature.EFFECT | LightEntityFeature.TRANSITION
