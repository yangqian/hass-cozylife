# CozyLife for Home Assistant

A Home Assistant custom integration for controlling CozyLife smart lights and switches over the local network. Communicates directly with devices via TCP — no cloud required.

## Features

- Pure local control over TCP (port 5555), no cloud dependency
- Supports color bulbs (RGB, color temperature, brightness) and switches
- Smooth transitions between brightness and color states
- Built-in lighting effects: manual, natural (circadian), sleep, warm, study, rainbow
- Automatic reconnection if a device goes offline and comes back
- Optional [Circadian Lighting](https://github.com/claytonjn/hass-circadian_lighting) integration

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=yangqian&repository=hass-cozylife&category=integration)

Or manually:

1. Open HACS in Home Assistant
2. Go to **Integrations** and click the three-dot menu
3. Select **Custom repositories**
4. Add `https://github.com/yangqian/hass-cozylife` as an **Integration**
5. Install **CozyLife** and restart Home Assistant

### Manual

Copy the `custom_components/cozylife` folder into your Home Assistant `custom_components` directory and restart.

## Setup

### Prerequisites

1. Initialize your CozyLife devices using the official CozyLife app (to connect them to your WiFi network)
2. Assign static IP addresses to your devices in your router
3. (Optional) Block internet access for the devices to prevent cloud communication

### Adding Devices

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **CozyLife**
3. Enter the IP range to scan (e.g. `192.168.1.1` to `192.168.1.254`)
4. All discovered CozyLife devices on that subnet will be added automatically

Devices on the same /24 subnet are grouped under a single hub entry.

## Tested Devices

- Color bulbs (with and without HomeKit support)
- Smart switches
- CW (cool/warm white) bulbs

## Notes

- Devices must have static IPs configured in your router
- All communication is unencrypted TCP on port 5555
- Color accuracy may vary between bulb models
