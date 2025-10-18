"""CozyLife integration setup for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_AREA, CONF_NAME, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN


PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CozyLife from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    entry_data: dict[str, object]

    if "devices" in entry.data:
        # Legacy configuration where a single entry represented a full scan.
        entry_data = {
            "devices": entry.data["devices"],
            "timeout": entry.data.get("timeout", 0.3),
            "scan_settings": {
                "start_ip": entry.data.get("start_ip"),
                "end_ip": entry.data.get("end_ip"),
                "timeout": entry.data.get("timeout", 0.3),
            },
        }
    else:
        device_info = dict(entry.data.get("device", {}))
        timeout = entry.data.get("timeout", 0.3)
        name_value = entry.data.get(CONF_NAME)
        if name_value is None:
            name_value = entry.data.get("name")

        area = entry.data.get(CONF_AREA)
        if area is None:
            area = entry.data.get("location")

        entry_data = {
            "device": device_info,
            "timeout": timeout,
            CONF_NAME: name_value,
            CONF_AREA: area,
        }

    hass.data[DOMAIN][entry.entry_id] = entry_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a CozyLife config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle migration of config entries."""

    # No migrations defined yet.
    return True
