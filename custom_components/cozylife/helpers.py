"""Helper utilities for CozyLife integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar


def normalize_area_value(area_value: Any) -> str | None:
    """Return a normalised area identifier or ``None``."""

    if isinstance(area_value, dict):
        area_value = area_value.get("area_id") or area_value.get("id")

    if isinstance(area_value, str):
        area_value = area_value.strip()

    if not area_value:
        return None

    return str(area_value)


def _lookup_area_id(area_registry: ar.AreaRegistry, area_value: str) -> str | None:
    """Resolve the provided value to an existing area identifier."""

    if area := area_registry.async_get_area(area_value):
        return area.id

    if area := area_registry.async_get_area_by_name(area_value):
        return area.id

    return None


def resolve_area_id(hass: HomeAssistant, area_value: Any) -> str | None:
    """Return a Home Assistant area ID for the provided value, if possible."""

    normalized = normalize_area_value(area_value)
    if not normalized:
        return None

    area_registry = ar.async_get(hass)
    return _lookup_area_id(area_registry, normalized)


def prepare_area_value_for_storage(
    hass: HomeAssistant, area_value: Any
) -> str | None:
    """Coerce user-provided area data into a stored representation."""

    normalized = normalize_area_value(area_value)
    if not normalized:
        return None

    area_registry = ar.async_get(hass)
    resolved = _lookup_area_id(area_registry, normalized)
    return resolved or normalized
