# Blueprints

Effektvakt kommer med fire blueprints i `docs/blueprints/`. De er laget for å brukes direkte, men kan tilpasses.

## Importer til Home Assistant

Lenkene under åpner import-dialogen i din egen HA:

- [Enkel lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fenkel_lastkutt.yaml): én switch av og på
- [Prioritert lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fprioritert_lastkutt.yaml): to switches i rekkefølge etter hvor nær terskelen timen ligger
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fclimate_min_temp.yaml): panelovn til min-temp med restore
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fkun_varsel.yaml): push-notifikasjon uten styring

---

## Hovedbryteren

Integrasjonen lager én switch per oppsett, `switch.effektvakt_automatikk`. Slår du den av, kutter ingen av blueprintene under, uansett hvor mange automasjoner du har laget. Den er på som standard og husker stillingen over omstart.

Alle fire blueprintene tar den inn som `automatikk_switch`. Feltet er valgfritt: lar du det stå tomt, oppfører automasjonen seg nøyaktig som før bryteren fantes, så eksisterende automasjoner overlever en oppdatering uten at du rører dem. Vil du at de skal lytte, må du peke feltet på bryteren.

Bryteren stopper bare kutt. Grenene som slår last på igjen er ikke gatet, for ellers kunne en varmtvannsbereder blitt stående av fordi noen vippet bryteren midt i et kutt. Slår du av mens et kutt pågår, kommer lasten tilbake når `max_off_minutes` løper ut. I `prioritert_lastkutt` skjer det med én gang: den faller gjennom til default-grenen som slår alt på.

Sensorene bryr seg ikke om bryteren. Projisert time-snitt, risiko og kostnad regnes videre, og `binary_sensor.effektvakt_kutt_ned_anbefalt` står fortsatt på når risikoen tilsier det. Den sier «dette burde kuttes», ikke «dette blir kuttet». Vil et dashboard vise begge deler, ligger bryterens stilling som attributtet `automatikk_aktiv` på den samme binary-sensoren.

---

## enkel_lastkutt.yaml

**Hva**: Slår av én switch når `binary_sensor.effektvakt_kutt_ned_anbefalt` går til `on`. Slår på igjen automatisk når sensoren går til `off`, eller etter `max_off_minutes` som failsafe.

**Passer til**: VVB, billader, panelovn med switch.

**Input**:

| Felt                   | Standard                                     | Beskrivelse                                |
| ---------------------- | -------------------------------------------- | ------------------------------------------ |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                        |
| `switch_entity`        | (ingen)                                      | Switchen som slås av                       |
| `automatikk_switch`    | (tom)                                        | Hovedbryteren, se under. Tom = kutt alltid |
| `max_off_minutes`      | 30                                           | Failsafe: tving på igjen etter N minutter  |

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
    automatikk_switch: switch.effektvakt_automatikk
    max_off_minutes: 30
```

---

## prioritert_lastkutt.yaml

**Hva**: Styrer to switches i prioritert rekkefølge basert på `sensor.effektvakt_risiko_niva`. Første switch slås av når timen ligger like under terskelen, begge når den er over.

**Passer til**: Situasjoner med to kuttbare laster der du vil rangere hvilken som kuttes først.

**Input**:

| Felt                     | Standard                        | Beskrivelse                    |
| ------------------------ | ------------------------------- | ------------------------------ |
| `risiko_sensor`          | `sensor.effektvakt_risiko_niva` | Effektvakt risiko-sensor       |
| `switch_high_priority`   | (ingen)                         | Kuttes først (like under)      |
| `switch_medium_priority` | (ingen)                         | Kuttes i tillegg (over)        |
| `automatikk_switch`      | (tom)                           | Hovedbryteren, se under        |
| `max_off_minutes`        | 30                              | Failsafe per switch            |

**Oppførsel**:

- `like_under_terskel`: switch 1 av, switch 2 på
- `over_terskel`: begge av, failsafe starter
- `naermer_seg_terskel` / `god_margin`: begge på

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - VVB og panelovn prioritert
use_blueprint:
  path: fredrik_lindseth/prioritert_lastkutt
  input:
    risiko_sensor: sensor.effektvakt_risiko_niva
    switch_high_priority: switch.varmtvannsbereder
    switch_medium_priority: switch.panelovn_stue
    automatikk_switch: switch.effektvakt_automatikk
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
| `automatikk_switch`    | (tom)                                        | Hovedbryteren, se under                 |
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
    automatikk_switch: switch.effektvakt_automatikk
    max_off_minutes: 30
```

---

## kun_varsel.yaml

**Hva**: Sender push-notifikasjon når risiko går til `like_under_terskel` eller `over_terskel`. Ingen styring av laster.

**Passer til**: Brukere som vil ta beslutningen selv basert på en notifikasjon.

**Input**:

| Felt                | Standard                        | Beskrivelse                                                 |
| ------------------- | ------------------------------- | ----------------------------------------------------------- |
| `risiko_sensor`     | `sensor.effektvakt_risiko_niva` | Effektvakt risiko-sensor                                    |
| `notify_service`    | `notify`                        | Tjeneste uten `notify.`-prefiks, f.eks. `mobile_app_iphone` |
| `automatikk_switch` | (tom)                           | Hovedbryteren, se under                                     |
| `dashboard_url`     | (tom)                           | URL til Lovelace-dashboard, lenkes i notifikasjon           |

**Oppførsel**:

- `like_under_terskel`: sender notifikasjon med projisert time-snitt og margin
- `over_terskel`: samme innhold, men tittelen sier at terskelen er passert
- Notifikasjoner køes (mode: queued) for å unngå tap ved rask endring

**Eksempel notifikasjonsinnhold**:

```
Effektvakt: like under terskelen
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
    automatikk_switch: switch.effektvakt_automatikk
    dashboard_url: /lovelace/effektvakt
```

---

## Failsafe-garanti

Alle blueprints med laststyring (enkel_lastkutt, prioritert_lastkutt, climate_min_temp) tvinger lasten tilbake etter `max_off_minutes`, uavhengig av hva Effektvakt rapporterer. Coordinatoren har i tillegg en watchdog som setter sensorer til `unknown` etter 2 minutter uten oppdatering. VVB-en din blir aldri stående av på ubestemt tid. Hovedbryteren endrer ikke dette: den hindrer nye kutt, men avbryter aldri en failsafe-timer som alt er i gang.
