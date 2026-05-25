# Effektvakt

Prediktiv kapasitetstrinn-styring for norske strømkunder i Home Assistant. Effektvakt forutsier om du er på vei mot å krysse neste kapasitetstrinn i nettleien og signaliserer kutt-anbefalinger gjennom sensorer du kobler til dine egne switches via medfølgende blueprints.

## Hvordan det virker

Norske nettselskap fakturerer kapasitetsledd etter snittet av topp-3 maks-timer fra ulike dager i måneden (NVE-modellen). Krysser du neste trinn én eneste time, betaler du for det trinnet resten av måneden. Effektvakt leser power- og energy-sensoren din, projiserer time-snittet, og varsler når en handling kan forhindre trinn-overskridelse.

## Installasjon

1. Installer via HACS (legg til som custom repository hvis ikke i default-listen).
2. Konfigurer integrasjonen: velg DSO, power-sensor, energy-sensor og innstillinger.
3. Importer en av blueprints nedenfor for å koble på styring.

## Sensorer

| Sensor | Hva |
|---|---|
| `sensor.effektvakt_projisert_time_snitt` | Forventet time-snitt i kW ved time-slutt |
| `sensor.effektvakt_margin_til_neste_trinn` | Hvor mange kW under neste trinn (etter topp-3-vurdering) |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | Snitt av topp-3 maks-timer fra ulike dager |
| `sensor.effektvakt_tilgjengelig_kutt` | Realistisk kutt-kapasitet i kW basert på valgt strategi |
| `sensor.effektvakt_risiko_niva` | none / low / medium / high (hysteresefull) |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on når kutt anbefales |

## Kutt-strategi

Effektvakt støtter tre strategier for å vurdere hvor mye effekt som realistisk kan kuttes:

- **Blind** (default): Antar 0,3 kW basert på typisk VVB duty cycle (15%). Ingen ekstra sensorer trengs.
- **VVB med statussensor**: Krever en sensor som rapporterer VVB-effekten. Gir reelt tall (typisk 0 eller ~2 kW).
- **VVB + billader**: Som over, pluss en billader-effektsensor. Største realistiske kutt-kapasitet.

Se [docs/faq.md](docs/faq.md) for hvorfor strategi-valg er viktig.

## Blueprints

Klikk for å importere blueprint direkte til ditt Home Assistant:

- [Enkel lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fenkel_lastkutt.yaml): én switch av/på basert på risiko
- [Prioritert lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fprioritert_lastkutt.yaml): flere switches i rekkefølge
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fclimate_min_temp.yaml): panelovner med restore-helper
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fkun_varsel.yaml): push-notifikasjon, ingen styring

## Dashboard-eksempel

Se [docs/dashboard-eksempel.yaml](docs/dashboard-eksempel.yaml) for en kopierbar Lovelace-konfigurasjon.

## Ofte stilte spørsmål

Lurer du på om det er trygt å skru av varmtvannstanken, hvor mye du faktisk sparer, eller hvilke laster som er smartest å kutte? Se [docs/faq.md](docs/faq.md).

## Failsafe

Alle lastkutt-blueprints har en `max_off_minutes`-input som tvinger lasten på igjen etter en tidsfrist, uavhengig av Effektvakts tilstand. Effektvakts coordinator har egen watchdog som setter sensorer til `unknown` hvis ingen oppdatering har skjedd på 2 minutter. Designet skal aldri etterlate VVB-en din av forever.

## Lisens

MIT. Se LICENSE.
