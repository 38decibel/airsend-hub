## Unreleased

### Added

### Changed
- **cleanup:** remove dead code and unused fields (inclusion, airsend_client, callback_server, catalog_data, yaml_import) (#62)

### Fixed

### Dependencies

## 0.29.0 - 2026-07-20

### Added

### Changed

### Fixed
- **client:** restore missing exception class bodies (#61)

### Dependencies

## 0.28.0 - 2026-07-20

### Added

### Changed

### Fixed
- comments translated to eng (#60)

### Dependencies

## 0.27.0 - 2026-07-20

### Added

### Changed
- fixed(cleanup): strip inline code comments (#59)

### Fixed

### Dependencies

## 0.26.1 - 2026-07-20

### Added

### Changed

### Fixed

### Dependencies

## 0.26.0 - 2026-07-19

### Added

### Changed

### Fixed
- **cover:** estimate assumed state from elapsed travel time on STOP instead of relying on MQTT's flawed stopped-state resolution (#57)

### Dependencies

## 0.25.0 - 2026-07-19

### Added

### Changed

### Fixed
- **cover:** use MQTT "optimistic" instead of non-existent "assumed_state" to keep volet_roulant buttons active (#56)

### Dependencies

## 0.24.0 - 2026-07-19

### Added
- **cover:** add configurable travel_time timer for volet_roulant end-of-travel state (#55)

### Changed

### Fixed

### Dependencies

## 0.23.0 - 2026-07-19

### Added

### Changed

### Fixed

### Dependencies

## 0.22.0 - 2026-07-19

### Added

### Changed

### Fixed

### Dependencies

## 0.21.3 - 2026-07-18

### Added

### Changed

### Fixed

### Dependencies

## 0.21.2 - 2026-07-18

### Added

### Changed
- add third-party licensing section for Devmel SDK (#54)

### Fixed

### Dependencies

## 0.21.1 - 2026-07-17

### Added

### Changed

### Fixed
- **catalog:** Add missing brands from official catalog (#53)

### Dependencies

## 0.21.0 - 2026-07-17

### Added
- **inclusion:** add brand-less generic 433MHz search (#52)

### Changed

### Fixed

### Dependencies

## 0.20.0 - 2026-07-16

### Added

### Changed

### Fixed
- **mqtt:** remove stale version state_class and retire the inclusion-mode switch (#51)

### Dependencies

## 0.19.0 - 2026-07-16

### Added

### Changed

### Fixed
- **mqtt:** give each RF element its own HA device instead of sharing the box device (#50)

### Dependencies

## 0.18.0 - 2026-07-16

### Added

### Changed

### Fixed
- **mqtt:** define missing constants in diagnostic sensor helper (#49)

### Dependencies

## 0.17.0 - 2026-07-16

### Added

### Changed

### Fixed
- **inclusion:** Targeted RF task subject to premature garbage collection (#48)

### Dependencies

## 0.16.1 - 2026-07-16

### Added

### Changed

### Fixed

### Dependencies
- chore(deps): update pyyaml requirement from <7,>=6.0 to >=6.0.3,<7 in /addons/airsend/rootfs/app in the python-dependencies group (#47)

## 0.16.0 - 2026-07-15

### Added

### Changed

### Fixed
- **inclusion:** fix premature end of targeted RF listen session (#46)

### Dependencies

## 0.15.0 - 2026-07-15

### Added

### Changed
- [WIP] Fix all currently open issues in repository (#45)

### Fixed

### Dependencies

## 0.14.1 - 2026-07-15

### Added

### Changed

### Fixed

### Dependencies

## 0.14.0 - 2026-07-15

### Added
- **inclusion:** ajoute l'import YAML depuis l'ancienne intégration hass_airsend (#31)

### Changed

### Fixed

### Dependencies

## 0.13.0 - 2026-07-14

### Added
- **inclusion-ui:** allow renaming, editing options and deleting devices (#30)

### Changed

### Fixed

### Dependencies

## 0.12.1 - 2026-07-14

### Added

### Changed

### Fixed

### Dependencies

## 0.12.0 - 2026-07-14

### Added
- **ingress:** New Ingress UI for device search and addition (#29)

### Changed

### Fixed

### Dependencies

## 0.11.0 - 2026-07-12

### Added

### Changed

### Fixed
- **cover:** stop publishing unsupported "unknown" MQTT state (#28)

### Dependencies

## 0.10.0 - 2026-07-11

### Added

### Changed

### Fixed
- **client:** serialize /airsend/transfer to avoid 500 under burst commands (#27)

### Dependencies

## 0.9.1 - 2026-07-11

### Added

### Changed

### Fixed
- **readme:** add little precision in final step (#26)

### Dependencies

## 0.9.0 - 2026-07-11

### Added

### Changed

### Fixed

### Dependencies
- chore(ci): généralise le changelog automatique et ajoute le lint de titre

## 0.8.0 - 2026-07-11

### Added

### Changed

### Fixed

### Dependencies
- Update callback_server.py

## 0.7.0 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.6.1 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.6.0 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies
- Update main.py

## 0.5.0 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.4.0 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.3.0 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.7 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.6 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.5 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.4 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.3 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.2 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

## 0.2.1 - 2026-07-10

### Added

### Changed

### Fixed

### Dependencies

# Changelog

## 0.1.0

- Initial release