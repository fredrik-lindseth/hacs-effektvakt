# Blueprints

Effektvakt kommer med fire blueprints i `docs/blueprints/`. De er laget for å brukes direkte, men kan tilpasses.

---

## enkel_lastkutt.yaml

**Hva**: Slår av én switch når `binary_sensor.effektvakt_kutt_ned_anbefalt` går til `on`. Slår på igjen automatisk når sensoren går til `off`, eller etter `max_off_minutes` som failsafe.

**Passer til**: VVB, billader, panelovn med switch.

**Input**:

| Felt                   | Standard                                     | Beskrivelse                               |
| ---------------------- | -------------------------------------------- | ----------------------------------------- |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                       |
| `switch_entity`        | (ingen)                                      | Switchen som slås av                      |
| `max_off_minutes`      | 30                                           | Failsafe: tving på igjen etter N minutter |

**Oppførsel**:

- Sensor `on`: switch slås av, timer starter
- Timer utløper: switch slås på (uavhengig av sensor)
- Sensor `off`: switch slås på umiddelbart

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - VVB kutt
use_blueprint:
  path: fredrik_lindseth/enkel_lastkutt
  input:
    binary_sensor_entity: binary_sensor.effektvakt_kutt_ned_anbefalt
    switch_entity: switch.varmtvannsbereder
    max_off_minutes: 30
```

---

## prioritert_lastkutt.yaml

**Hva**: Styrer to switches i prioritert rekkefølge basert på `sensor.effektvakt_risiko_niva`. Første switch slås av ved medium risiko, begge ved high risiko.

**Passer til**: Situasjoner med to kuttbare laster der du vil rangere hvilken som kuttes først.

**Input**:

| Felt                     | Standard                        | Beskrivelse                    |
| ------------------------ | ------------------------------- | ------------------------------ |
| `risiko_sensor`          | `sensor.effektvakt_risiko_niva` | Effektvakt risiko-sensor       |
| `switch_high_priority`   | (ingen)                         | Kuttes først (medium risiko)   |
| `switch_medium_priority` | (ingen)                         | Kuttes i tillegg (high risiko) |
| `max_off_minutes`        | 30                              | Failsafe per switch            |

**Oppførsel**:

- `medium` risiko: switch 1 av, switch 2 på
- `high` risiko: begge av, failsafe starter
- `low` / `none`: begge på

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - VVB og panelovn prioritert
use_blueprint:
  path: fredrik_lindseth/prioritert_lastkutt
  input:
    risiko_sensor: sensor.effektvakt_risiko_niva
    switch_high_priority: switch.varmtvannsbereder
    switch_medium_priority: switch.panelovn_stue
    max_off_minutes: 30
```

---

## climate_min_temp.yaml

**Hva**: Setter en climate-entitet (panelovn) til min-temp når kutt anbefales, og restorer til lagret temperatur når risiko er borte. En `input_number`-hjelper persisterer temperaturen over HA-restart.

**Passer til**: Panelovner og andre climate-entiteter der du ikke vil slå av helt, men redusere setpunkt.

**Input**:

| Felt                   | Standard                                     | Beskrivelse                             |
| ---------------------- | -------------------------------------------- | --------------------------------------- |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                     |
| `climate_entity`       | (ingen)                                      | Panelovn eller annen climate            |
| `min_temp`             | 10 °C                                        | Setpunkt under kutt                     |
| `restore_helper`       | (ingen)                                      | `input_number` for å lagre forrige temp |
| `max_off_minutes`      | 30                                           | Failsafe: restore etter N minutter      |

**Sett opp `input_number` manuelt**:

```yaml
input_number:
  panelovn_stue_restore_temp:
    name: Panelovn stue - restore-temp
    min: 5
    max: 30
    step: 0.5
    unit_of_measurement: °C
```

**Oppførsel**:

- Sensor `on`: lagre nåværende temp i `input_number`, sett climate til `min_temp`, start timer
- Timer utløper: restore (uten å lese sensor)
- Sensor `off`: restore til lagret temp
- HA-restart: restore til lagret temp (trigger på `homeassistant.start`)

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - Panelovn stue
use_blueprint:
  path: fredrik_lindseth/climate_min_temp
  input:
    binary_sensor_entity: binary_sensor.effektvakt_kutt_ned_anbefalt
    climate_entity: climate.panelovn_stue
    min_temp: 10
    restore_helper: input_number.panelovn_stue_restore_temp
    max_off_minutes: 30
```

---

## kun_varsel.yaml

**Hva**: Sender push-notifikasjon når risiko går til `medium` eller `high`. Ingen styring av laster.

**Passer til**: Brukere som vil ta beslutningen selv basert på en notifikasjon.

**Input**:

| Felt             | Standard                        | Beskrivelse                                                 |
| ---------------- | ------------------------------- | ----------------------------------------------------------- |
| `risiko_sensor`  | `sensor.effektvakt_risiko_niva` | Effektvakt risiko-sensor                                    |
| `notify_service` | `notify`                        | Tjeneste uten `notify.`-prefiks, f.eks. `mobile_app_iphone` |
| `dashboard_url`  | (tom)                           | URL til Lovelace-dashboard, lenkes i notifikasjon           |

**Oppførsel**:

- `medium` risiko: sender notifikasjon med projisert time-snitt og margin
- `high` risiko: sender notifikasjon med `HIGH` i tittelen
- Notifikasjoner køes (mode: queued) for å unngå tap ved rask endring

**Eksempel notifikasjonsinnhold**:

```
Effektvakt: MEDIUM risiko
Projisert time-snitt: 9.7 kW. Margin: 0.3 kW.
```

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - Varsel til telefon
use_blueprint:
  path: fredrik_lindseth/kun_varsel
  input:
    risiko_sensor: sensor.effektvakt_risiko_niva
    notify_service: mobile_app_min_iphone
    dashboard_url: /lovelace/effektvakt
```

---

## Failsafe-garanti

Alle blueprints med laststyring (enkel_lastkutt, prioritert_lastkutt, climate_min_temp) tvinger lasten tilbake etter `max_off_minutes`, uavhengig av hva Effektvakt rapporterer. Coordinatoren har i tillegg en watchdog som setter sensorer til `unknown` etter 2 minutter uten oppdatering. VVB-en din blir aldri stående av på ubestemt tid.
