"""Config flow for the CozyLife integration."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .discovery import discover_devices

DEFAULT_START_IP = "192.168.0.0"
DEFAULT_END_IP = "192.168.0.255"


def _coerce_ip(value: str) -> str:
    """Validate and normalise an IPv4 address string."""

    try:
        return str(ipaddress.ip_address(value))
    except ValueError as err:
        raise vol.Invalid("invalid_ip") from err


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("start_ip", default=DEFAULT_START_IP): str,
        vol.Required("end_ip", default=DEFAULT_END_IP): str,
        vol.Optional("timeout", default=0.3): vol.All(
            vol.Coerce(float), vol.Range(min=0.05, max=10.0)
        ),
    }
)

class CozyLifeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the CozyLife config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_devices: list[dict[str, Any]] = []
        self._scan_settings: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step initiated by the user."""

        errors: dict[str, str] = {}

        if user_input is not None:
            start_ip = user_input.get("start_ip", "")
            end_ip = user_input.get("end_ip", "")

            try:
                start_ip = _coerce_ip(start_ip)
            except vol.Invalid:
                errors["start_ip"] = "invalid_ip"

            try:
                end_ip = _coerce_ip(end_ip)
            except vol.Invalid:
                errors["end_ip"] = "invalid_ip"

            if not errors and int(ipaddress.ip_address(start_ip)) > int(
                ipaddress.ip_address(end_ip)
            ):
                errors["end_ip"] = "range_order"

            if not errors:
                timeout = float(user_input["timeout"])

                devices = await self.hass.async_add_executor_job(
                    discover_devices, start_ip, end_ip, timeout
                )

                if not devices["lights"] and not devices["switches"]:
                    errors["base"] = "no_devices_found"
                else:
                    self._scan_settings = {
                        "start_ip": start_ip,
                        "end_ip": end_ip,
                        "timeout": timeout,
                    }
                    self._discovered_devices = [
                        *devices["lights"],
                        *devices["switches"],
                    ]
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or {}
            ),
            errors=errors,
            description_placeholders={
                "start": DEFAULT_START_IP,
                "end": DEFAULT_END_IP,
            },
        )

    async def async_step_device(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Allow the user to select a discovered device and configure it."""

        errors: dict[str, str] = {}

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        device_choices: dict[str, str] = {}
        for device in self._discovered_devices:
            label_type = device.get("type", "device").capitalize()
            model = device.get("dmn") or "Unknown"
            label = f"{label_type}: {model} ({device['ip']})"
            device_choices[device["did"]] = label

        if user_input is not None:
            selected = user_input.get("device")
            if selected not in device_choices:
                errors["device"] = "device_missing"
            else:
                if any(
                    entry.unique_id == selected for entry in self._async_current_entries()
                ):
                    errors["device"] = "already_configured"
                else:
                    device = next(
                        item for item in self._discovered_devices if item["did"] == selected
                    )

                    name_input = (user_input.get("name") or "").strip()
                    location_input = (user_input.get("location") or "").strip()

                    title = name_input or device.get("dmn") or device["did"]

                    data = {
                        "device": device,
                        "timeout": self._scan_settings["timeout"],
                        "name": name_input or None,
                        "location": location_input or None,
                    }

                    await self.async_set_unique_id(device["did"])
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(title=title, data=data)

        if user_input is not None:
            suggested_name = user_input.get("name", "")
            suggested_location = user_input.get("location", "")
        else:
            suggested_name = ""
            suggested_location = ""

        device_field = vol.Required("device")
        if len(device_choices) == 1:
            (device_id, _) = next(iter(device_choices.items()))
            device_field = vol.Required("device", default=device_id)

        schema = vol.Schema(
            {
                device_field: vol.In(device_choices),
                vol.Optional("name", default=suggested_name): str,
                vol.Optional("location", default=suggested_location): str,
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler."""

        return CozyLifeOptionsFlow(config_entry)


class CozyLifeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the CozyLife integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options for the integration."""

        errors: dict[str, str] = {}

        data = self.config_entry.data

        if "device" not in data:
            return await self._async_step_legacy(user_input)

        device = data.get("device", {})

        if user_input is not None:
            ip_value = user_input.get("ip", "")
            timeout_value = user_input.get("timeout")
            name_value = (user_input.get("name") or "").strip()
            location_value = (user_input.get("location") or "").strip()

            try:
                ip_value = _coerce_ip(ip_value)
            except vol.Invalid:
                errors["ip"] = "invalid_ip"

            try:
                timeout_value = float(timeout_value)
            except (TypeError, ValueError):
                errors["timeout"] = "invalid_timeout"
            else:
                if not 0.05 <= timeout_value <= 10.0:
                    errors["timeout"] = "invalid_timeout"

            if not errors:
                updated_device = {**device, "ip": ip_value}
                updated_data = {
                    **data,
                    "device": updated_device,
                    "timeout": timeout_value,
                    "name": name_value or None,
                    "location": location_value or None,
                }

                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=updated_data
                )
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        suggested_name = data.get("name") or device.get("dmn") or device.get("did")
        suggested_location = data.get("location") or ""
        suggested_ip = device.get("ip", "")
        suggested_timeout = data.get("timeout", 0.3)

        options_schema = vol.Schema(
            {
                vol.Required("ip", default=suggested_ip): str,
                vol.Required("timeout", default=suggested_timeout): vol.Coerce(float),
                vol.Optional("name", default=suggested_name or ""): str,
                vol.Optional("location", default=suggested_location): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema, user_input or {}
            ),
            errors=errors,
        )

    async def _async_step_legacy(
        self, user_input: Mapping[str, Any] | None
    ) -> FlowResult:
        """Handle options for legacy search-based entries."""

        errors: dict[str, str] = {}

        if user_input is not None:
            start_ip = user_input.get("start_ip", "")
            end_ip = user_input.get("end_ip", "")

            try:
                start_ip = _coerce_ip(start_ip)
            except vol.Invalid:
                errors["start_ip"] = "invalid_ip"

            try:
                end_ip = _coerce_ip(end_ip)
            except vol.Invalid:
                errors["end_ip"] = "invalid_ip"

            if not errors and int(ipaddress.ip_address(start_ip)) > int(
                ipaddress.ip_address(end_ip)
            ):
                errors["end_ip"] = "range_order"

            if not errors:
                timeout = float(user_input["timeout"])

                devices = await self.hass.async_add_executor_job(
                    discover_devices, start_ip, end_ip, timeout
                )

                if not devices["lights"] and not devices["switches"]:
                    errors["base"] = "no_devices_found"
                else:
                    data = {
                        "start_ip": start_ip,
                        "end_ip": end_ip,
                        "timeout": timeout,
                        "devices": devices,
                    }
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=data
                    )
                    await self.hass.config_entries.async_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(title="", data={})

        current = self.config_entry.data
        suggested = {
            "start_ip": current.get("start_ip"),
            "end_ip": current.get("end_ip"),
            "timeout": current.get("timeout", 0.3),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, suggested
            ),
            errors=errors,
        )
