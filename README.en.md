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

At BKK, the 5–10 kW capacity tier costs NOK 165 more per month than the 2–5 kW tier. Avoiding the higher tier in two to four months means **NOK 330–660 less in annual grid charges**, without necessarily using less electricity. Five such months would mean NOK 825. EV charging, water heating and space heating provide flexibility; the result depends on your peaks and how much demand you can defer.

These are conditional calculations, not measured savings. For an example home using 16,000 kWh/year, NOK 330–660 is about 2–4% of combined electricity and grid costs. See the [annual calculation](docs/sparepotensial.md#hva-kan-det-bli-på-et-år), [laundry during cheaper grid periods](docs/scenario-nattvask.md) and [Norgespris versus spot prices](docs/scenario-norgespris.md).

## A savings example from BKK

Reducing the monthly top-three average by 1 kW would have lowered a BKK household's capacity charge by NOK 165 in December 2025 and NOK 165 in February 2026: NOK 330 in total. A 600 W reduction would not have reached the cheaper tier. This is conditional potential calculated from historical readings; the load must run for long enough, and deferred heating must fit into later hours. See the [calculation and simulation](docs/sparepotensial.md) and [an example load-profile report](docs/research/lastprofil-rapport.md).

<p align="center">
  <img src="docs/bilder/skive-gossen.png" alt="Effektvakt dashboard card: an analogue demand monitor with a kW scale, monthly capacity prices and three indicators" width="420">
</p>

## How it works

Effektvakt projects the current hourly average and compares it with your monthly capacity tier. Sensors show the margin, risk, monthly top-three average and measured load reduction available now. You can use notifications or blueprints to control water heaters, heating and other loads. The load guard restores controlled loads by their deadline and retains responsibility across reloads and restarts.

The calculation supports tariffs based on the three highest hourly averages from different days. Household tariffs are built in; custom tiers must use the same method. Missing or stale power readings give unknown advice. [Strømkalkulator](https://github.com/fredrik-lindseth/hacs-strømkalkulator) calculates grid charges, taxes and support schemes. Avoiding a capacity tier saves money without necessarily reducing kWh. Nord Pool price scheduling is not implemented.

Setup, entities and the card support Norwegian and English. Detailed guides are in Norwegian.

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

Then go to **Settings > Devices & Services > Add Integration > Effektvakt**. Choose your grid company and power sensor; the remaining settings have defaults. See the [setup guide](docs/oppsett.md).

## Dashboard and load control

Add `custom:effektvakt-card` to your dashboard; see the [card setup](docs/dashboard-kort.md). The red indicator is the projected hourly average, the thin black indicator is current power, and the outer triangle is the monthly top-three average.

<p align="center">
  <img src="docs/bilder/dashboard.png" alt="Dashboard with the demand dial, remaining-hour cards and weekly chart" width="900">
</p>

Register your controllable loads under Configure and import the [blueprints](docs/blueprints.md) for notifications or automatic reductions. Set maximum off-time and minimum on-time to suit each load. The [load-profile guide](docs/lastprofiler.md) explains how to estimate what a load can contribute during the rest of the hour.

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
