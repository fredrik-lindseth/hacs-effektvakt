# Effektvakt

[Norsk](README.md) · English

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest"><img src="https://img.shields.io/github/v/release/fredrik-lindseth/hacs-effektvakt" alt="Release"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/ci.yml"><img src="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/validate.yml"><img src="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/validate.yml/badge.svg" alt="HACS Validation"></a>
  <a href="https://app.codecov.io/gh/fredrik-lindseth/hacs-effektvakt"><img src="https://codecov.io/gh/fredrik-lindseth/hacs-effektvakt/branch/main/graph/badge.svg" alt="Codecov"></a>
</p>

Effektvakt projects your average consumption for the current hour and warns when it could push you into a more expensive grid capacity tier. It is a Home Assistant integration for electricity customers in Norway.

## What could you save?

At BKK, moving from the 5–10 kW tier to 2–5 kW saves **NOK 165 per month**. Two to four such months mean NOK 330–660/year; five mean NOK 825. EV charging, water heating and space heating can provide flexibility to shift peaks.

This is conditional potential. For an example home using 16,000 kWh/year, NOK 330–660 represents about 2–4% of combined electricity and grid costs. See the [annual calculation and assumptions](docs/sparepotensial.md#hva-kan-det-bli-på-et-år).

## A savings example from BKK

A 1 kW lower top-three average would have reduced capacity charges by NOK 330 across December 2025 and February 2026; 600 W would not have been enough. Duration and reheating determine feasibility. [Historical figures and simulation](docs/sparepotensial.md).

<p align="center">
  <img src="docs/bilder/skive-gossen.png" alt="Effektvakt dashboard card: an analogue demand monitor with a kW scale, monthly capacity prices and three indicators" width="420">
</p>

## How it works

Sensors show the projected hourly average, margin, risk, monthly top-three average and available reductions. Use notifications or blueprints to control loads; the load guard retains responsibility for restoration across restarts.

Supports tariffs using the three highest hourly averages from different days. Missing or stale readings give unknown advice. Automatic spot-price scheduling is not implemented. [Strømkalkulator](https://github.com/fredrik-lindseth/hacs-strømkalkulator) calculates grid charges, taxes and support schemes.

Setup, sensors and the card support Norwegian and English. Detailed guides are in Norwegian.

## Installation

Requires Home Assistant 2025.1.0 or newer.

### HACS

Open Effektvakt in HACS with the button. If the repository has not been added yet, follow the steps below.

[![Open Effektvakt in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fredrik-lindseth&repository=hacs-effektvakt&category=integration)

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/fredrik-lindseth/hacs-effektvakt` with type **Integration**.
3. Download **Effektvakt** and restart Home Assistant.

### Manual installation

Download `effektvakt.zip` from the [latest release](https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest) and extract it into `/config/custom_components/effektvakt`. Restart Home Assistant.

Add it under **Settings → Devices & Services → Add Integration → Effektvakt**, then choose your grid company and power sensor. [Setup](docs/oppsett.md).

## Dashboard and load control

Add `custom:effektvakt-card` to your dashboard. [Card setup and indicators](docs/dashboard-kort.md).

<p align="center">
  <img src="docs/bilder/dashboard.png" alt="Dashboard with the demand dial, remaining-hour cards and weekly chart" width="900">
</p>

Register [loads](docs/laster.md) under Configure and import [blueprints](docs/blueprints.md) for notifications or reductions. Choose time limits to suit each load; [profiles](docs/lastprofiler.md) estimate the remaining-hour contribution.

## Quality and development

CI tests the promised minimum and current Home Assistant versions, checks HACS and hassfest, and requires 95% combined test coverage. [Codecov](https://app.codecov.io/gh/fredrik-lindseth/hacs-effektvakt) publishes the reports. See the [development guide](docs/development.md) for environments and commands.

## Documentation

| Document | Contents |
| --- | --- |
| [Savings potential](docs/sparepotensial.md) | Monthly target and historical simulation |
| [Laundry during cheaper grid periods](docs/scenario-nattvask.md) | Consumption, timing and grid charges |
| [Norgespris or spot prices](docs/scenario-norgespris.md) | Price schemes and a higher Norgespris |
| [Load profiles](docs/lastprofiler.md) | Method, local analysis and interpretation |
| [Measurement report](docs/research/lastprofil-rapport.md) | Synthetic example and reporting guide |
| [Setup](docs/oppsett.md) | Configuration step by step |
| [Sensors](docs/sensorer.md) | Sensors and attributes |
| [Calculations](docs/beregninger.md) | Formulas and calculation logic |
| [Input sensors](docs/input-sensorer.md) | Sensor requirements and known sources |
| [Loads](docs/laster.md) | Controllable loads and thresholds |
| [Blueprints](docs/blueprints.md) | Import, inputs and examples |
| [Dashboard card](docs/dashboard-kort.md) | Lovelace card |
| [Physical panel](docs/fysisk-panel.md) | ESP32 panel concept, not built |
| [Limitations](docs/begrensninger.md) | Known limitations |
| [DSO data](docs/dso.md) | Tariff data and updates |
| [Development](docs/development.md) | Developer guide |
| [FAQ](docs/faq.md) | Frequently asked questions |

## License

MIT. See [LICENSE](LICENSE).
