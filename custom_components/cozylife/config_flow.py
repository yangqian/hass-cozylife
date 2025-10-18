"""Config flow for the CozyLife integration."""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import network, selector

from .const import CONF_AREA, DOMAIN
from .helpers import (
    normalize_area_value,
    prepare_area_value_for_storage,
    resolve_area_id,
)
from .discovery import discover_devices

DEFAULT_START_IP = "192.168.0.0"
DEFAULT_END_IP = "192.168.0.255"

_LOGGER = logging.getLogger(__name__)


def _coerce_ip(value: str) -> str:
    """Validate and normalise an IPv4 address string."""

    try:
        return str(ipaddress.ip_address(value))
    except ValueError as err:
        raise vol.Invalid("invalid_ip") from err


TIMEOUT_VALIDATOR = vol.All(vol.Coerce(float), vol.Range(min=0.05, max=10.0))

LEGACY_RANGE_SCHEMA = vol.Schema(
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
        self._auto_scan_ranges: list[tuple[str, str]] = []

    async def _async_get_auto_scan_ranges(self) -> list[tuple[str, str]]:
        """Return the automatically detected scan ranges for the host network."""

        if self._auto_scan_ranges:
            return self._auto_scan_ranges

        ranges: list[tuple[str, str]] = []

        try:
            adapters = await network.async_get_adapters(self.hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to determine network adapters: %s", err)
            adapters = []

        seen: set[tuple[str, str]] = set()

        for adapter in adapters:
            if not adapter.get("enabled", True):
                continue

            for ipv4_data in adapter.get("ipv4", []):
                if ipv4_data.get("scope") not in (None, "global"):
                    continue

                address = ipv4_data.get("address")
                netmask = ipv4_data.get("netmask")

                if not address or not netmask:
                    continue

                try:
                    interface = ipaddress.IPv4Interface(f"{address}/{netmask}")
                except ValueError:
                    continue

                network_details = interface.network

                start = str(network_details.network_address)
                end = str(network_details.broadcast_address)

                if (start, end) in seen:
                    continue

                seen.add((start, end))
                ranges.append((start, end))

        self._auto_scan_ranges = ranges
        return self._auto_scan_ranges

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step initiated by the user."""

        errors: dict[str, str] = {}

        detected_auto_ranges = await self._async_get_auto_scan_ranges()
        effective_auto_ranges = (
            detected_auto_ranges
            if detected_auto_ranges
            else [(DEFAULT_START_IP, DEFAULT_END_IP)]
        )

        suggested_start = (
            user_input.get("start_ip")
            if user_input and "start_ip" in user_input
            else effective_auto_ranges[0][0]
        )
        suggested_end = (
            user_input.get("end_ip")
            if user_input and "end_ip" in user_input
            else effective_auto_ranges[0][1]
        )
        suggested_timeout = (
            user_input.get("timeout")
            if user_input and "timeout" in user_input
            else 0.3
        )

        use_custom_range = bool(user_input and user_input.get("use_custom_range"))
        if (
            not use_custom_range
            and user_input is not None
            and (user_input.get("start_ip") or user_input.get("end_ip"))
        ):
            # Treat manual IP input as opting into custom mode even if the
            # toggle was not explicitly enabled.
            use_custom_range = True

        show_manual_fields = use_custom_range

        if user_input is not None:
            try:
                timeout = TIMEOUT_VALIDATOR(user_input.get("timeout", 0.3))
            except vol.Invalid:
                errors["timeout"] = "invalid_timeout"
                timeout = 0.3
            else:
                suggested_timeout = timeout

            ranges_to_scan: list[tuple[str, str]] = []

            if use_custom_range:
                start_ip = user_input.get("start_ip", "")
                end_ip = user_input.get("end_ip", "")

                if not start_ip or not end_ip:
                    errors["base"] = "manual_range_required"
                else:
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
                        ranges_to_scan = [(start_ip, end_ip)]
            else:
                ranges_to_scan = effective_auto_ranges

            if not errors and ranges_to_scan:
                discovered: dict[str, list[dict[str, Any]]] = {
                    "lights": [],
                    "switches": [],
                }
                seen_devices: set[str] = set()

                for start_ip, end_ip in ranges_to_scan:
                    devices = await self.hass.async_add_executor_job(
                        discover_devices, start_ip, end_ip, timeout
                    )

                    for device in devices["lights"]:
                        if device["did"] in seen_devices:
                            continue
                        seen_devices.add(device["did"])
                        discovered["lights"].append(device)

                    for device in devices["switches"]:
                        if device["did"] in seen_devices:
                            continue
                        seen_devices.add(device["did"])
                        discovered["switches"].append(device)

                if not discovered["lights"] and not discovered["switches"]:
                    errors["base"] = "no_devices_found"
                else:
                    self._scan_settings = {
                        "mode": "custom" if use_custom_range else "auto",
                        "ranges": ranges_to_scan,
                        "timeout": timeout,
                    }
                    unique_devices: dict[str, dict[str, Any]] = {
                        item["did"]: item
                        for item in [
                            *discovered["lights"],
                            *discovered["switches"],
                        ]
                    }
                    self._discovered_devices = sorted(
                        unique_devices.values(),
                        key=lambda item: (
                            item.get("type", ""),
                            item.get("dmn") or "",
                            item.get("ip") or "",
                        ),
                    )
                    return await self.async_step_device()

        description_default_start = (
            suggested_start if suggested_start else effective_auto_ranges[0][0]
        )
        description_default_end = (
            suggested_end if suggested_end else effective_auto_ranges[0][1]
        )

        placeholders = {
            "auto": ", ".join(
                f"{start} – {end}" for start, end in detected_auto_ranges
            )
            if detected_auto_ranges
            else f"{DEFAULT_START_IP} – {DEFAULT_END_IP}",
            "protocol": "a TCP probe on port 5555",
            "default_range": f"{description_default_start} – {description_default_end}",
        }

        schema = self._build_user_schema(
            show_manual_fields,
            suggested_start,
            suggested_end,
            suggested_timeout,
            use_custom_range,
        )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input or {},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    def _build_user_schema(
        show_manual_fields: bool,
        suggested_start: str,
        suggested_end: str,
        suggested_timeout: float,
        use_custom_range: bool,
    ) -> vol.Schema:
        """Construct the dynamic schema for the user step."""

        schema_fields: dict[Any, Any] = {
            vol.Required("use_custom_range", default=use_custom_range): bool,
        }

        if show_manual_fields:
            schema_fields.update(
                {
                    vol.Required("start_ip", default=suggested_start): str,
                    vol.Required("end_ip", default=suggested_end): str,
                }
            )

        schema_fields[vol.Required("timeout", default=suggested_timeout)] = TIMEOUT_VALIDATOR

        return vol.Schema(schema_fields)

    async def async_step_device(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Allow the user to select a discovered device and configure it."""

        errors: dict[str, str] = {}

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        type_labels = {
            "light": "Light",
            "switch": "Switch",
        }

        device_choices: dict[str, str] = {}
        device_options: list[selector.SelectOptionDict] = []
        for device in self._discovered_devices:
            device_id = device["did"]
            label_type = type_labels.get(
                device.get("type"),
                (device.get("type") or "device").replace("_", " ").title(),
            )
            model = device.get("dmn") or "Unknown"
            label = f"{label_type}: {model} ({device['ip']})"
            device_choices[device_id] = label
            device_options.append(
                selector.SelectOptionDict(value=device_id, label=label)
            )

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

                    name_input = (user_input.get(CONF_NAME) or "").strip()
                    area_input = prepare_area_value_for_storage(
                        self.hass, user_input.get(CONF_AREA)
                    )

                    title = name_input or device.get("dmn") or device["did"]

                    data = {
                        "device": device,
                        "timeout": self._scan_settings["timeout"],
                        CONF_NAME: name_input or None,
                        CONF_AREA: area_input or None,
                    }

                    await self.async_set_unique_id(device["did"])
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(title=title, data=data)

        if user_input is not None:
            suggested_name = user_input.get(CONF_NAME, "")
            suggested_area = normalize_area_value(user_input.get(CONF_AREA))
        else:
            suggested_name = ""
            suggested_area = None

        device_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=device_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        device_field = vol.Required("device")
        if len(device_choices) == 1:
            (device_id, _) = next(iter(device_choices.items()))
            device_field = vol.Required("device", default=device_id)

        schema = vol.Schema(
            {
                device_field: device_selector,
                vol.Optional(CONF_NAME, default=suggested_name): selector.TextSelector(),
                vol.Optional(CONF_AREA, default=suggested_area): selector.AreaSelector(),
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
            name_value = (user_input.get(CONF_NAME) or "").strip()
            area_value = prepare_area_value_for_storage(
                self.hass, user_input.get(CONF_AREA)
            )

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
                    CONF_NAME: name_value or None,
                    CONF_AREA: area_value or None,
                }

                if "location" in updated_data:
                    updated_data.pop("location", None)
                if "name" in updated_data and CONF_NAME in updated_data:
                    updated_data.pop("name", None)

                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=updated_data
                )
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        suggested_name = (
            data.get(CONF_NAME)
            or data.get("name")
            or device.get("dmn")
            or device.get("did")
        )
        raw_area = data.get(CONF_AREA) or data.get("location") or None
        suggested_area = resolve_area_id(self.hass, raw_area)
        suggested_ip = device.get("ip", "")
        suggested_timeout = data.get("timeout", 0.3)

        options_schema = vol.Schema(
            {
                vol.Required("ip", default=suggested_ip): str,
                vol.Required("timeout", default=suggested_timeout): vol.Coerce(float),
                vol.Optional(CONF_NAME, default=suggested_name or ""): selector.TextSelector(),
                vol.Optional(CONF_AREA, default=suggested_area): selector.AreaSelector(),
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
                LEGACY_RANGE_SCHEMA, suggested
            ),
            errors=errors,
        )
