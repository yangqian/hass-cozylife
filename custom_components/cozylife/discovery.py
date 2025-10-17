"""Discovery helpers for CozyLife devices."""

from __future__ import annotations

from ipaddress import ip_address
import logging

from .const import LIGHT_TYPE_CODE, SWITCH_TYPE_CODE
from .tcp_client import tcp_client

_LOGGER = logging.getLogger(__name__)


def _ip_range(start: str, end: str) -> list[str]:
    """Generate a list of IP addresses within the inclusive range."""

    start_int = int(ip_address(start))
    end_int = int(ip_address(end))

    if start_int > end_int:
        start_int, end_int = end_int, start_int

    return [str(ip_address(ip)) for ip in range(start_int, end_int + 1)]


def discover_devices(start_ip: str, end_ip: str, timeout: float = 0.3) -> dict[str, list[dict[str, object]]]:
    """Scan an IP range for CozyLife devices."""

    lights: list[dict[str, object]] = []
    switches: list[dict[str, object]] = []

    for address in _ip_range(start_ip, end_ip):
        client = tcp_client(address, timeout=timeout)

        try:
            client._initSocket()

            if not client._connect:
                continue

            client._device_info()

            if not client._device_id or not client._device_type_code:
                continue

            device_data = {
                "ip": address,
                "did": client._device_id,
                "pid": client._pid,
                "dpid": list(client._dpid) if isinstance(client._dpid, list) else client._dpid,
                "dmn": client._device_model_name,
            }

            if client._device_type_code == LIGHT_TYPE_CODE:
                lights.append(device_data)
            elif client._device_type_code == SWITCH_TYPE_CODE:
                switches.append(device_data)

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Error discovering CozyLife device at %s: %s", address, err)
        finally:
            client.disconnect()

    return {"lights": lights, "switches": switches}
