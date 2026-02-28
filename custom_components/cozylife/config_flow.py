"""Config flow for CozyLife integration."""
from __future__ import annotations

import logging
from ipaddress import ip_address

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_DEVICE_TYPE_CODE,
    SUPPORT_DEVICE_CATEGORY,
)
from .tcp_client import tcp_client

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
    }
)


class CozyLifeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CozyLife."""

    VERSION = 1

    @staticmethod
    def _probe_device(ip: str) -> dict | None:
        """Probe a device at the given IP (runs in executor)."""
        client = tcp_client(ip, timeout=3)
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

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step — user enters an IP address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_IP_ADDRESS].strip()
            data = await self.hass.async_add_executor_job(
                self._probe_device, ip
            )
            if data is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data["did"])
                self._abort_if_unique_id_configured(updates={"ip": ip})
                return self.async_create_entry(
                    title=data["dmn"],
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict) -> FlowResult:
        """Handle import from YAML configuration."""
        await self.async_set_unique_id(import_data["did"])
        self._abort_if_unique_id_configured(updates={"ip": import_data["ip"]})
        return self.async_create_entry(
            title=import_data.get("dmn", "CozyLife Device"),
            data=import_data,
        )
