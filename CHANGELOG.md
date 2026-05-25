# Endringslogg

Følger [Keep a Changelog](https://keepachangelog.com/) og [SemVer](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-05-25

### Endret

- `CONF_BILLADER_POWER_SENSOR` (single) erstattet med `CONF_EKSTRA_POWER_SENSORS` (liste)
- Strategi `vvb_billader` omdøpt til `vvb_pluss_ekstra` (gammel navn aksepteres for bakoverkompatibilitet)
- Ekstra-power-sensorer som er over 100 W summeres og bidrar til `tilgjengelig_kutt_kw`

### Bruksanvisning

Nå kan du legge inn flere varmekabler, billader, osv som ekstra-sensorer for å få realistisk kutt-kapasitet.

## [0.2.0] - 2026-05-25

### Lagt til

- `CONF_KUTT_STRATEGI`: tre strategier (blind / vvb_status / vvb_billader)
- `CONF_VVB_POWER_SENSOR`: optional sensor for å garantere reelle kutt
- `CONF_BILLADER_POWER_SENSOR`: optional sensor for stor enkeltlast
- Ny sensor: `sensor.effektvakt_tilgjengelig_kutt` (kW)
- Config flow og options flow utvidet med strategi-velger

## [0.1.0] - 2026-05-25

### Lagt til

- Initial release.
- Coordinator med NVE-modell (topp-3 dager), effective_threshold, adaptiv tick.
- 4 sensorer + 1 binary_sensor.
- 4 blueprints (enkel, prioritert, climate, kun varsel) med max_off_minutes-failsafe.
- Watchdog uavhengig av coordinator.
- DSO-sync-script mot strømkalkulator.
- Replay-test mot BKK-fixturer.
