"""Config flow for CozyLife integration."""
from __future__ import annotations

import logging
from ipaddress import IPv4Address, ip_address

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_DEVICE_TYPE_CODE,
    CONF_SUBNET,
    CONF_DEVICES,
    SUPPORT_DEVICE_CATEGORY,
)
from .tcp_client import tcp_client

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("start_ip"): str,
        vol.Required("end_ip"): str,
    }
)


def _get_subnet(ip: str) -> str:
    """Return the /24 subnet prefix for an IP address (e.g. '192.168.1')."""
    parts = ip.split(".")
    return ".".join(parts[:3])


class CozyLifeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CozyLife."""

    VERSION = 2

    @staticmethod
    def _probe_device(ip: str) -> dict | None:
        """Probe a single device at the given IP."""
        client = tcp_client(ip, timeout=0.5)
        try:
            client._initSocket()
            if not client._connect:
                return None
            client._device_info()
            if not client._connect:
                return None
            if not hasattr(client, '_device_id') or not isinstance(client._device_id, str):
                return None
            if not hasattr(client, '_device_type_code') or client._device_type_code not in SUPPORT_DEVICE_CATEGORY:
                return None
            return {
                "ip": ip,
                "did": client._device_id,
                "pid": client._pid,
                "dmn": client._device_model_name,
                "dpid": client._dpid,
                CONF_DEVICE_TYPE_CODE: client._device_type_code,
            }
        except Exception:
            _LOGGER.exception("Error probing device at %s", ip)
            return None
        finally:
            client.disconnect()

    @staticmethod
    def _scan_range(start_ip: str, end_ip: str) -> list[dict]:
        """Scan an IP range and return a list of discovered device dicts."""
        start_int = int(IPv4Address(start_ip))
        end_int = int(IPv4Address(end_ip))
        devices = []
        for ip_int in range(start_int, end_int + 1):
            ip = str(IPv4Address(ip_int))
            result = CozyLifeConfigFlow._probe_device(ip)
            if result is not None:
                devices.append(result)
        return devices

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step — user enters an IP range."""
        errors: dict[str, str] = {}

        if user_input is not None:
            start_ip = user_input["start_ip"].strip()
            end_ip = user_input["end_ip"].strip()

            # Validate IPs
            try:
                start_addr = ip_address(start_ip)
                end_addr = ip_address(end_ip)
            except ValueError:
                errors["base"] = "invalid_ip"
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                )

            # Must be same /24 subnet
            if _get_subnet(start_ip) != _get_subnet(end_ip):
                errors["base"] = "different_subnet"
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                )

            # End must be >= start
            if int(start_addr) > int(end_addr):
                errors["base"] = "invalid_range"
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                )

            subnet = _get_subnet(start_ip)

            # Abort if this subnet hub already exists
            await self.async_set_unique_id(subnet)
            self._abort_if_unique_id_configured()

            # Scan
            devices = await self.hass.async_add_executor_job(
                self._scan_range, start_ip, end_ip
            )

            if not devices:
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                )

            return self.async_create_entry(
                title=f"CozyLife Hub ({subnet}.0/24)",
                data={
                    CONF_SUBNET: subnet,
                    "start_ip": start_ip,
                    "end_ip": end_ip,
                    CONF_DEVICES: devices,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict) -> FlowResult:
        """Handle import from YAML configuration.

        Groups devices by /24 subnet. If a hub entry for the subnet already
        exists, the device is appended to that entry and a reload is scheduled.
        """
        subnet = _get_subnet(import_data["ip"])

        # Check if a hub entry for this subnet already exists
        for entry in self._async_current_entries():
            if entry.data.get(CONF_SUBNET) == subnet:
                # Append device if not already present
                existing_dids = {d["did"] for d in entry.data.get(CONF_DEVICES, [])}
                if import_data["did"] in existing_dids:
                    return self.async_abort(reason="already_configured")

                new_devices = list(entry.data[CONF_DEVICES]) + [import_data]
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_DEVICES: new_devices},
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(entry.entry_id)
                )
                return self.async_abort(reason="device_added_to_hub")

        # No hub for this subnet yet — create one
        await self.async_set_unique_id(subnet)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"CozyLife Hub ({subnet}.0/24)",
            data={
                CONF_SUBNET: subnet,
                "start_ip": f"{subnet}.1",
                "end_ip": f"{subnet}.254",
                CONF_DEVICES: [import_data],
            },
        )
