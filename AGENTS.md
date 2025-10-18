# Repository Guidelines for Automation and Versioning

- Keep HACS metadata updates manual. When preparing a release, bump the version field in `custom_components/cozylife/manifest.json` explicitly and, if needed, adjust `hacs.json` manually.
- Do **not** introduce workflows or scripts that automatically commit or push version changes on merge. Follow the standard HACS approach of using Git tags or deliberate commits for versioning.
# CozyLife Home Assistant Integration Overview

This repository contains a custom Home Assistant integration for controlling CozyLife smart devices over the local network. The integration is organised around a thin asynchronous layer that orchestrates Home Assistant config entries and entities, while delegating device communication to a synchronous TCP client.

## Architecture
- **Entry point (`custom_components/cozylife/__init__.py`)** – registers the integration, stores per-entry runtime data in `hass.data[DOMAIN]`, and forwards setup/unload calls to the supported platforms (currently `light` and `switch`).
- **Config flow (`config_flow.py`)** – drives onboarding. It can automatically derive scan ranges from the host network, perform manual range scans, discover compatible devices, and persist the selected device plus metadata (friendly name, location, timeout). Options flow allows tweaking IP, timeout, and labels after setup. Legacy entries created from a full-range scan remain supported.
- **Platforms (`light.py`, `switch.py`)** – define entity classes that adapt CozyLife devices to Home Assistant platforms. They wrap a per-device TCP client, expose properties such as name, availability, and brightness, and schedule periodic state refreshes via executor jobs because device I/O is blocking.
- **Discovery helpers (`discovery.py`)** – iterate over an IPv4 range, instantiating `tcp_client` objects to probe each address on port 5555. Devices are classified using the CozyLife type codes (`const.py`) and returned for config-flow selection.
- **TCP client (`tcp_client.py`)** – implements the proprietary binary-on-JSON protocol used by CozyLife hardware. It opens the TCP socket, requests device metadata, issues state queries, and sends control commands. Device capabilities are resolved against a cached `model.json` catalogue through helpers in `utils.py`.

## Features
- Automatic and manual LAN discovery of CozyLife lights and switches.
- Native Home Assistant config/option flows with validation for IP ranges and network timeouts.
- Support for per-device metadata (name, location) that maps to Home Assistant entity attributes and suggested areas.
- Periodic polling of device state with graceful handling of offline devices.
- Local-only communication over TCP port 5555 without relying on cloud services.

## Implementation Notes
- Blocking socket calls are isolated to executor jobs (`hass.async_add_executor_job`) to keep Home Assistant's event loop responsive.
- Device identifiers (`did`), product identifiers (`pid`), and datapoint IDs (`dpid`) discovered via the TCP client are cached in `hass.data` for reuse by platforms.
- `utils.get_pid_list` reads `model.json` once per runtime, caching the device catalogue in memory to minimise disk I/O and provide device names/icons.
- Constants in `const.py` centralise device type codes, datapoint IDs, and manufacturer metadata that are shared across modules.
