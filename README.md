# Effektvakt

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/releases"><img src="https://img.shields.io/github/release/fredrik-lindseth/hacs-effektvakt.svg" alt="GitHub release"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/ci.yml"><img src="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/validate.yml"><img src="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/validate.yml/badge.svg" alt="HACS Validation"></a>
</p>

Prediktiv kapasitetstrinn-styring for norske strømkunder i Home Assistant.

## Hva du får

Effektvakt projiserer time-snittet ditt og varsler deg før du krysser neste kapasitetstrinn i nettleien:

- Projisert time-snitt i kW ved slutten av inneværende time
- Margin til neste kapasitetstrinn, med topp-3-dager-bevissthet
- Risiko-nivå (none/low/medium/high) med hysterese
- Realistisk kutt-kapasitet basert på valgt strategi
- Binary sensor som blueprints kan handle direkte på
- Fire medfølgende blueprints for VVB, panelovner og varsler
- Watchdog: sensorer settes til `unknown` hvis coordinator henger

## Hvordan det virker

Norske nettselskap fakturerer kapasitetsleddet etter snittet av de tre høyeste time-snittene fra ulike dager i måneden (NVE-modellen). Krysser du neste trinn én eneste time, betaler du for det trinnet resten av måneden.

Effektvakt leser power- og energy-sensoren din hvert 15-60 sekund. Den projiserer time-snittet ved time-slutt basert på hva som er brukt og hva som brukes nå. Marginen sammenlignes mot terskelen for neste trinn, justert for hvilke av topp-3-dagene som allerede er registrert denne måneden. Risiko-nivået oppdateres med hysterese for å unngå hyppig av/på-flakking.

## Installasjon

### HACS

1. Legg til dette repoet som custom repository i HACS: `fredrik-lindseth/hacs-effektvakt`, kategori **Integration**.
2. Klikk **Download**.
3. Start Home Assistant på nytt.

### Manuell

Kopier `custom_components/effektvakt` til `/config/custom_components/`.

## Oppsett

**Settings > Devices & Services > Add Integration > Effektvakt**

### Steg 1: Velg nettselskap

Velg nettselskapet ditt fra listen (72 støttede DSO-er). Kapasitetstrinnene og prisene hentes automatisk. Mangler du ditt nettselskap, eller bruker du egendefinerte trinn, velger du **Egendefinert** og legger inn tersklene manuelt.

### Steg 2: Velg sensorer

| Sensor | Krav | Beskrivelse |
|---|---|---|
| Power-sensor | Påkrevd | Instantan effekt (W eller kW), oppdateres hvert 2-10 sek |
| Energy-sensor | Anbefalt | Kumulativ kWh-måler, `total_increasing` |
| VVB-power-sensor | Valgfri | Krevd for strategi `vvb_status` og `vvb_pluss_ekstra` |
| Ekstra power-sensorer | Valgfri | Krevd for strategi `vvb_pluss_ekstra` |

Se [docs/input-sensorer.md](docs/input-sensorer.md) for detaljer om sensorkrav og kjente kilder.

### Steg 3: Innstillinger

| Innstilling | Standard | Beskrivelse |
|---|---|---|
| Sikkerhetsbuffer (kW) | 1,0 | Margin under terskelen som trigger `medium`-risiko |
| Min risiko for kutt | medium | Under dette nivået er `binary_sensor` av |
| Risiko-holdetid (min) | 5 | Hvor lenge nedgang i risiko må holde seg før det bekreftes |
| Kutt-strategi | blind | Se [Kutt-strategi](#kutt-strategi) |

## Sensorer

| Sensor | Enhet | Beskrivelse |
|---|---|---|
| `sensor.effektvakt_projisert_time_snitt` | kW | Forventet time-snitt ved time-slutt |
| `sensor.effektvakt_margin_til_neste_trinn` | kW | Margin fra projisert til neste trinn (negativ = overskredet) |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | kW | Snitt av topp-3 maks-timer fra ulike dager denne måneden |
| `sensor.effektvakt_risiko_niva` | enum | none / low / medium / high |
| `sensor.effektvakt_tilgjengelig_kutt` | kW | Realistisk kutt-kapasitet basert på strategi |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on/off | on når risiko >= min_risiko_for_kutt |

Alle sensorer har felles attributter med detaljer om beregningene. Se [docs/sensorer.md](docs/sensorer.md).

## Kutt-strategi

Strategien styrer hva `sensor.effektvakt_tilgjengelig_kutt` rapporterer. Den påvirker ikke risiko-vurderingen, som alltid baserer seg på projisert time-snitt mot trinnterskel.

| Strategi | Sensorer | Beskrivelse |
|---|---|---|
| `blind` | Ingen | Antar 0,3 kW (VVB duty cycle ~15%). Standardvalg. |
| `vvb_status` | VVB-power-sensor | Faktisk VVB-effekt i kW. Typisk 0 eller ~2 kW. |
| `vvb_pluss_ekstra` | VVB + ekstra | VVB pluss sum av ekstra-sensorer (varmekabler, billader). |

Se [docs/strategi.md](docs/strategi.md) for når-bruke-hva og eksempel-tall.

## Blueprints

Importer direkte til Home Assistant:

- [Enkel lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fenkel_lastkutt.yaml): én switch av/på basert på `binary_sensor.effektvakt_kutt_ned_anbefalt`
- [Prioritert lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fprioritert_lastkutt.yaml): to switches i rekkefølge basert på medium/high risiko
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fclimate_min_temp.yaml): panelovn til min-temp med input_number-restore
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fkun_varsel.yaml): push-notifikasjon uten styring

Se [docs/blueprints.md](docs/blueprints.md) for konfigurasjon og eksempler.

## Failsafe

Alle lastkutt-blueprints har `max_off_minutes` som tvinger lasten på igjen etter en tidsfrist, uavhengig av Effektvakts tilstand. Coordinatoren har en watchdog som setter alle sensorer til `unknown` hvis ingen oppdatering har skjedd på 2 minutter. VVB-en din blir aldri stående av på ubestemt tid.

## Dokumentasjon

| Dokument | Innhold |
|---|---|
| [docs/sensorer.md](docs/sensorer.md) | Alle sensorer og attributter |
| [docs/beregninger.md](docs/beregninger.md) | Formler og beregningslogikk |
| [docs/input-sensorer.md](docs/input-sensorer.md) | Sensorkrav og kjente kilder |
| [docs/blueprints.md](docs/blueprints.md) | Blueprint-detaljer og eksempler |
| [docs/strategi.md](docs/strategi.md) | Kutt-strategier sammenlignet |
| [docs/begrensninger.md](docs/begrensninger.md) | Kjente begrensninger |
| [docs/dso.md](docs/dso.md) | DSO-data og oppdatering |
| [docs/development.md](docs/development.md) | Utvikler-guide |
| [docs/faq.md](docs/faq.md) | Ofte stilte spørsmål |

## Lisens

MIT. Se LICENSE.
