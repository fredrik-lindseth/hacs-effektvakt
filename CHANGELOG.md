# Endringslogg

Følger [Keep a Changelog](https://keepachangelog.com/) og [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-05-25

### Lagt til

- Initial release.
- Coordinator med NVE-modell (topp-3 dager), effective_threshold, adaptiv tick.
- 4 sensorer + 1 binary_sensor.
- 4 blueprints (enkel, prioritert, climate, kun varsel) med max_off_minutes-failsafe.
- Watchdog uavhengig av coordinator.
- DSO-sync-script mot strømkalkulator.
- Replay-test mot BKK-fixturer.
