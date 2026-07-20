# Home Assistant App: AirSend-Hub

All-in-one AirSend controller for Home Assistant: device inclusion, MQTT bridge and web UI in a single add-on.

![Supports aarch64 Architecture][aarch64-shield] ![Supports armhf Architecture][armhf-shield] ![Supports arm Architecture][arm-shield] ![Supports x86_64 Architecture][x86_64-shield] ![Supports x86 Architecture][x86-shield]

## About

You can use this app (formerly known as add-on) to use the AirSend (RF433) or AirSend Duo (RF433 & RF868) in transmission and reception. An Airsend box device is created in MQTT. Each newly discovered device is pushed as a new device and linked to Airsend box. For more information, please see [devmel].

## ✨ Features

This addon is a ground-up rebuild of the AirSend integration for Home Assistant, focused on a self-service experience that doesn't require editing YAML by hand or permit inclusion of new device.

- **Guided device inclusion via the UI** — a step-by-step Ingress wizard lets you pick a brand, listen for RF events, and confirm the detected device, with or without a physical remote in hand. No manual `airsend.yaml` editing required to add a device.
- **No auto-include, no surprises** — nothing is created in Home Assistant without explicit user confirmation. Every detected candidate is reviewed before it becomes an entity.
- **MQTT discovery, not YAML mapping** — entities are created and updated through Home Assistant's native MQTT discovery, so there's no `type` code to look up and no addon restart needed after adding a device.
- **One RF element, one HA device** — each button, shutter, or switch is exposed as its own Home Assistant device (with `via_device` pointing to the AirSend box), following the same hub-and-child-device pattern as Zigbee2MQTT or Z-Wave JS UI — instead of being buried as an entity under a single monolithic integration device.
- **`airsend.yaml` import, if you have one** — devices already defined for the official integration can be imported and reviewed through a preview screen with conflict detection, so migrating existing setups doesn't mean starting from scratch.
- **Built-in inclusion of "orphan" or unrecognized devices** — devices and protocols not in the official catalog (e.g. proprietary Profalux/PFX RF frames) can still be captured and added based on raw RF event data, rather than being limited to the vendor's official device list.
- **Editable/removable devices from the UI** — every device can be renamed, reconfigured, or deleted directly from the Ingress panel, no file editing involved.
- 
## Installation
<p align="center">
    <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F38decibel%2Fairsend-hub">
        <img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Open your Home Assistant instance and show the add apps repository dialog with a specific repository URL pre-filled.">
    </a>
</p>

## How to use

To get the app running:

0. Disable (or uninstall) the official `hass_airsend-addon` and the
   official `hass_airsend` integration first, to avoid both addons
   controlling the same AirSend box and to keep the same entitie's name (they will be recreated by this new app)
1. Fill 'Boxes Airsend' fields in configuration tab
2. Optional: add MQTT informations to connect an external MQTT broker. Leave blank will use the built-in MQTT broker of HA.
3. Run the app
4. Check your MQTT broker to see the AirSend device.
5. Devices already known to the addon (e.g. imported from a previous setup) are automatically discovered by Home Assistant as covers, switches, or other entities via MQTT.
6. To add a new device, open the **AirSend** panel from the Home Assistant sidebar (Ingress UI). See below for import airsend.yaml file.
7. Choose the inclusion method depending on what you have on hand:
   - **With the original remote**: select it from the catalog, then follow the on-screen steps to trigger the RF listening window and press the remote's button.
   - **Without the remote**: enter the channel source manually. If a conflict is detected (HTTP 409), the addon will warn you about rolling-code resynchronization before proceeding.
8. Once included, the new device appears automatically in Home Assistant via MQTT discovery — no restart required.
9. Repeat step 6-8 for each additional device.

## How to import airsend.yaml from the official addon

If you were previously using Devmel's official `hass_airsend-addon`, you can
import your existing devices instead of re-configuring them from scratch.

1. Locate your `airsend.yaml` file. It is stored in your Home Assistant
   main config folder (the same folder as `configuration.yaml`).
2. Open the **AirSend** panel from the Home Assistant sidebar (Ingress UI).
3. Go to the **Import** section and choose one of the two options:
   - **Upload file**: select your `airsend.yaml` directly.
   - **Paste content**: open `airsend.yaml` in a text editor, copy its
     content, and paste it into the text field provided.
4. Confirm the import. Devices found in the file are added to this addon's
   device list and will appear in Home Assistant via MQTT discovery.
5. Review the imported devices in the AirSend panel — some fields (e.g.
   friendly names) may need adjustment depending on differences between the
   official addon's format and this addon's device model.

### App configuration

```yaml
boxes:
  - localip: fe80::dcf6:e5ff:feXX:XXXX #Local IP written on the label under the box
    password: PASSWORD #Password written on the label under the box
    ipv4: 192.168.XXX.XXX #IPv4 given by your router
    gw: true
    name: AIRSEND_XXXXX #Name that will be created in MQTT
```
### Option: `system` (optional)

```yaml
system:
    log_level: ERROR # Allowed values: `ERROR`,`WARNING`,`INFO`,`DEBUG`
```

### Option: `MQTT` (optional)

```yaml
mqtt:
    host: core-mosquitto
    port: 1883
    ssl: true
    username: user
    password: passwd
```

## Third-party components & licensing

### AirSendWebService binary (Devmel)

This addon downloads and executes the `AirSendWebService` binary at build
time from [Devmel]'s official distribution URL. It is used unmodified, solely
through its local HTTP API, under the terms of the Devmel SDK license
(see [`./THIRD_PARTY_LICENSES/DevmelSDK.txt`](./THIRD_PARTY_LICENSES/DevmelSDK.txt)).

This app is an independent, community-built project. **It is not
officially affiliated with, endorsed by, or supported by Devmel.** Devmel's
own official addon is
[`hass_airsend-addon`](https://github.com/devmel/hass_airsend-addon), and
their custom integration (HACS) is
[`hass_airsend`](https://github.com/devmel/hass_airsend).

Per that license, the binary is provided **as-is**, without warranty or
guaranteed support from Devmel. Issues in this addon's own code can be
reported via this repository's issue tracker; issues intrinsic to the RF
gateway firmware or the binary itself are outside this project's control.

[devmel]: https://devmel.com/

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[arm-shield]: https://img.shields.io/badge/arm-yes-green.svg
[x86_64-shield]: https://img.shields.io/badge/x86_64-yes-green.svg
[x86-shield]: https://img.shields.io/badge/x86-yes-green.svg
