"""CozyLife integration."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EFFECT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_DEVICE_TYPE_CODE,
    CONF_SUBNET,
    CONF_DEVICES,
    PLATFORMS,
)
from .tcp_client import tcp_client

_LOGGER = logging.getLogger(__name__)

# Key for storing light entity references for set_all_effect service
LIGHT_ENTITIES_KEY = "light_entities"

# Entry IDs that were absorbed into a hub during consolidation
_ABSORBED_IDS_KEY = "_absorbed_ids"


def _get_subnet(ip: str) -> str:
    """Return the /24 subnet prefix for an IP address."""
    parts = ip.split(".")
    return ".".join(parts[:3])


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a v1 per-device config entry to v2 hub format.

    The first entry migrated for a given subnet becomes the hub (unique_id =
    subnet).  Subsequent entries for the same subnet merge their device into
    the hub and receive a throw-away unique_id so no duplicates are created.
    """
    if entry.version >= 2:
        return True

    _LOGGER.info("Migrating CozyLife config entry %s from v1 to v2", entry.entry_id)
    data = dict(entry.data)
    subnet = _get_subnet(data["ip"])
    device = {
        "ip": data["ip"],
        "did": data["did"],
        "pid": data.get("pid", "p93sfg"),
        "dmn": data.get("dmn", "CozyLife Device"),
        "dpid": data.get("dpid", [1]),
        CONF_DEVICE_TYPE_CODE: data.get(CONF_DEVICE_TYPE_CODE, "01"),
    }

    # Check if a hub entry for this subnet was already created by a prior
    # migration in this same startup cycle.
    existing_hub = None
    for other in hass.config_entries.async_entries(DOMAIN):
        if (
            other.entry_id != entry.entry_id
            and other.version >= 2
            and other.data.get(CONF_SUBNET) == subnet
            and other.data.get(CONF_DEVICES)  # non-empty → real hub
        ):
            existing_hub = other
            break

    if existing_hub:
        # Merge device into the existing hub
        hub_devices = list(existing_hub.data.get(CONF_DEVICES, []))
        if device["did"] not in {d["did"] for d in hub_devices}:
            hub_devices.append(device)
            hass.config_entries.async_update_entry(
                existing_hub,
                data={**existing_hub.data, CONF_DEVICES: hub_devices},
            )
        # Convert this entry to an empty "absorbed" entry with a unique id
        hass.config_entries.async_update_entry(
            entry,
            version=2,
            data={CONF_SUBNET: subnet, CONF_DEVICES: []},
            unique_id=f"_absorbed_{data['did']}",
        )
        _LOGGER.info(
            "Merged device %s into hub for %s, entry %s marked for removal",
            data["did"], subnet, entry.entry_id,
        )
    else:
        # First entry for this subnet — becomes the hub
        new_data = {
            CONF_SUBNET: subnet,
            "start_ip": f"{subnet}.1",
            "end_ip": f"{subnet}.254",
            CONF_DEVICES: [device],
        }
        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            unique_id=subnet,
            title=f"CozyLife Hub ({subnet}.0/24)",
            version=2,
        )
        _LOGGER.info("Entry %s is now the hub for subnet %s", entry.entry_id, subnet)

    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the CozyLife component.

    Handles consolidation of duplicate v2 entries that share the same subnet
    (e.g. from a previous migration that created duplicates).
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(LIGHT_ENTITIES_KEY, [])

    # Consolidation: group v2 entries by subnet, merge devices, mark extras
    entries = hass.config_entries.async_entries(DOMAIN)
    by_subnet: dict[str, list[ConfigEntry]] = {}
    for entry in entries:
        subnet = entry.data.get(CONF_SUBNET)
        if subnet and entry.data.get(CONF_DEVICES):
            # Only group entries that have devices (skip already-absorbed empties)
            by_subnet.setdefault(subnet, []).append(entry)

    absorbed_ids: set[str] = set()

    for subnet, group in by_subnet.items():
        if len(group) <= 1:
            continue

        _LOGGER.info(
            "Consolidating %d CozyLife entries for subnet %s", len(group), subnet
        )
        primary = group[0]
        merged_devices = list(primary.data.get(CONF_DEVICES, []))
        seen_dids = {d["did"] for d in merged_devices}

        for extra in group[1:]:
            for dev in extra.data.get(CONF_DEVICES, []):
                if dev["did"] not in seen_dids:
                    merged_devices.append(dev)
                    seen_dids.add(dev["did"])
            absorbed_ids.add(extra.entry_id)

        hass.config_entries.async_update_entry(
            primary,
            data={**primary.data, CONF_DEVICES: merged_devices},
        )

    # Also mark entries that have empty device lists (from migration absorption)
    for entry in entries:
        if entry.data.get(CONF_SUBNET) and not entry.data.get(CONF_DEVICES):
            absorbed_ids.add(entry.entry_id)

    hass.data[DOMAIN][_ABSORBED_IDS_KEY] = absorbed_ids

    # Remove absorbed entries now (before async_setup_entry is called)
    for entry_id in absorbed_ids:
        _LOGGER.info("Removing absorbed config entry %s", entry_id)
        await hass.config_entries.async_remove(entry_id)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a CozyLife hub from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(LIGHT_ENTITIES_KEY, [])

    # Safety net: if this entry was absorbed but not yet removed, remove it now
    absorbed = hass.data[DOMAIN].get(_ABSORBED_IDS_KEY, set())
    devices = entry.data.get(CONF_DEVICES, [])
    if entry.entry_id in absorbed or not devices:
        _LOGGER.info("Skipping absorbed/empty entry %s, scheduling removal", entry.entry_id)
        hass.async_create_task(
            hass.config_entries.async_remove(entry.entry_id)
        )
        return True

    clients: dict[str, tcp_client] = {}

    for dev in devices:
        client = tcp_client(dev["ip"])
        client._device_id = dev["did"]
        client._pid = dev["pid"]
        client._dpid = dev["dpid"]
        client._device_model_name = dev.get("dmn", "CozyLife Device")
        client._device_type_code = dev.get(CONF_DEVICE_TYPE_CODE, "01")
        await hass.async_add_executor_job(client._initSocket)
        clients[dev["did"]] = client

    hass.data[DOMAIN][entry.entry_id] = {
        "clients": clients,
        "devices": devices,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    """Unload a CozyLife hub config entry."""
    # If entry was never fully set up (absorbed), just return True
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return True

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry_data and "clients" in entry_data:
            for client in entry_data["clients"].values():
                await hass.async_add_executor_job(client.disconnect)

    return ok
