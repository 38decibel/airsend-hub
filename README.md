# Home Assistant App: AirSend

AirSend controller for Home Assistant.

![Supports aarch64 Architecture][aarch64-shield] ![Supports armhf Architecture][armhf-shield] ![Supports arm Architecture][arm-shield] ![Supports x86_64 Architecture][x86_64-shield] ![Supports x86 Architecture][x86-shield]

## About

You can use this app (formerly known as add-on) to use the AirSend (RF433) or AirSend Duo (RF433 & RF868) in transmission and reception. An Airsend device is created in MQTT. Each newly discovered device is pushed as a new entity. For more information, please see [devmel].

## Installation
<p align="center">
    <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F38decibel%2Fairsend-addon-dev">
        <img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Open your Home Assistant instance and show the add apps repository dialog with a specific repository URL pre-filled.">
    </a>
</p>

## How to use

To get the app running:

1. Fill 'Boxes Airsend' fields in configuration tab
2. Optional : add MQTT informations to connect an external MQTT broker. Leave blank will use the built-in MQTT broker of HA.
3. Run the app
5. Check your MQTT broker to see the AirSend device.
6. Toggle the inclusion switch and push a button on your RF remote
7. ...Next steps need to be written !

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
    log_level: ERROR # Allowed values: `NONE`, `DEBUG`, `ERROR`, `WARNING`
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




[devmel]: https://devmel.com/

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[arm-shield]: https://img.shields.io/badge/arm-yes-green.svg
[x86_64-shield]: https://img.shields.io/badge/x86_64-yes-green.svg
[x86-shield]: https://img.shields.io/badge/x86-yes-green.svg
