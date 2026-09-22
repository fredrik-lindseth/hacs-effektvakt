# Blueprints

Effektvakt kommer med fire blueprints i `docs/blueprints/`. De er laget for å brukes direkte, men kan tilpasses.

## Installer

Kopier filene fra `docs/blueprints/` til `config/blueprints/automation/effektvakt/` i Home Assistant-oppsettet ditt, og last inn automasjoner på nytt (**Developer tools > YAML > Automations**). Da ligger de under `effektvakt/`, og det er stien eksemplene i dette dokumentet bruker.

Lenkene under åpner import-dialogen i din egen HA i stedet:

- [Enkel lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fenkel_lastkutt.yaml): én switch av og på
- [Prioritert lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fprioritert_lastkutt.yaml): to switches i rekkefølge etter hvor nær terskelen timen ligger
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fclimate_min_temp.yaml): panelovn til min-temp med restore
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fkun_varsel.yaml): push-notifikasjon uten styring

Importerer du sånn, legger Home Assistant filen under GitHub-kontoen url-en peker på, altså `fredrik-lindseth/enkel_lastkutt.yaml`. Setter du automasjonen opp i grensesnittet, trenger du ikke tenke på det. Skriver du YAML selv, må `path` peke på mappen filen faktisk havnet i, og alltid med `.yaml` bak.

---

## Hovedbryteren

Integrasjonen lager én switch per oppsett, `switch.effektvakt_automatikk`. Slår du den av, kutter ingen av lastkutt-blueprintene under, uansett hvor mange automasjoner du har laget. Den er på som standard og husker stillingen over omstart.

Alle fire blueprintene tar den inn som `automatikk_switch`. Feltet er valgfritt: lar du det stå tomt, oppfører automasjonen seg nøyaktig som før bryteren fantes, så eksisterende automasjoner overlever en oppdatering uten at du rører dem. Vil du at de skal lytte, må du peke feltet på bryteren.

Bryteren stopper bare kutt. Grenene som slår last på igjen er ikke gatet, for ellers kunne en varmtvannsbereder blitt stående av fordi noen vippet bryteren midt i et kutt. Slår du av mens et kutt pågår, kommer lasten tilbake ved neste timeskifte. I `prioritert_lastkutt` skjer det med én gang: den faller gjennom til default-grenen som slår alt på.

`kun_varsel` er unntaket. Den gater ikke på bryteren i det hele tatt. Har du skrudd av automatikken, er det du som må kutte, og da er varselet verdt mer, ikke mindre. Den sier i stedet fra i teksten at ingenting kuttes av seg selv.

Sensorene bryr seg ikke om bryteren. Projisert time-snitt, risiko og kostnad regnes videre, og `binary_sensor.effektvakt_kutt_ned_anbefalt` står fortsatt på når risikoen tilsier det. Den sier «dette burde kuttes», ikke «dette blir kuttet». Vil et dashboard vise begge deler, ligger bryterens stilling som attributtet `automatikk_aktiv` på den samme binary-sensoren.

---

## Kuttet slippes ved timeskiftet

Nettleien måles time for time. Et kutt som starter 18:50 og varer til 19:20 gir ti minutter nytte og tjue minutter kutting som bare flytter oppvarmingen inn i 19-timen og drar den opp. Derfor slipper alle tre lastkutt-blueprintene lasten ved neste hele time, eller når Effektvakt sier at risikoen er over, det som kommer først.

Det er også den enkleste demperen mot yo-yo: uten den varmer berederen 2 kW ekstra fra 19:05, drar 19-timen over terskelen, og blir kuttet på nytt. Hysteresen i integrasjonen hjelper ikke der, for det skjer på tvers av timer.

Er risikoen fortsatt der i den nye timen, kuttes lasten igjen, men først etter `min_on_minutes` på. Den påtiden er det som skiller et slipp fra en pause på null sekunder.

`max_off_minutes` er blitt et absolutt tak i stedet for hovedregelen. Kommer timeskiftet aldri, for eksempel fordi HA står i en rar tilstand, slippes lasten når taket nås. Standard er 60 minutter, som er akkurat lengre enn det lengste et kutt kan vare når timeskiftet virker.

---

## enkel_lastkutt.yaml

**Hva**: Slår av én switch når `binary_sensor.effektvakt_kutt_ned_anbefalt` går til `on`. Slår på igjen ved neste hele time, eller med én gang sensoren går til `off`.

**Passer til**: VVB, billader, panelovn med switch.

**Input**:

| Felt                   | Standard                                     | Beskrivelse                                 |
| ---------------------- | -------------------------------------------- | ------------------------------------------- |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                         |
| `switch_entity`        | (ingen)                                      | Switchen som slås av                        |
| `automatikk_switch`    | (tom)                                        | Hovedbryteren, se over. Tom = kutt alltid   |
| `max_off_minutes`      | 60                                           | Absolutt tak hvis timeskiftet aldri kommer  |
| `min_on_minutes`       | 5                                            | Minste påtid før lasten kan kuttes på nytt  |

**Oppførsel**:

- Sensor `on`: switch slås av
- Neste hele time: switch slås på
- Sensor `off`: switch slås på umiddelbart
- Fortsatt `on` etter påtiden: nytt kutt i den nye timen
- Taket nås: switch slås på uavhengig av sensor

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - VVB kutt
use_blueprint:
  path: effektvakt/enkel_lastkutt.yaml
  input:
    binary_sensor_entity: binary_sensor.effektvakt_kutt_ned_anbefalt
    switch_entity: switch.varmtvannsbereder
    automatikk_switch: switch.effektvakt_automatikk
    max_off_minutes: 60
    min_on_minutes: 5
```

---

## prioritert_lastkutt.yaml

**Hva**: Styrer to switches i prioritert rekkefølge basert på `sensor.effektvakt_risiko_niva`. Første switch slås av når timen ligger like under terskelen, begge når den er over.

**Passer til**: Situasjoner med to kuttbare laster der du vil rangere hvilken som kuttes først.

**Input**:

| Felt                     | Standard                        | Beskrivelse                                |
| ------------------------ | ------------------------------- | ------------------------------------------ |
| `risiko_sensor`          | `sensor.effektvakt_risiko_niva` | Effektvakt risiko-sensor                   |
| `switch_high_priority`   | (ingen)                         | Kuttes først (like under)                  |
| `switch_medium_priority` | (ingen)                         | Kuttes i tillegg (over)                    |
| `automatikk_switch`      | (tom)                           | Hovedbryteren, se over                     |
| `max_off_minutes`        | 60                              | Absolutt tak hvis timeskiftet aldri kommer |
| `min_on_minutes`         | 5                               | Minste påtid før nytt kutt                 |

**Oppførsel**:

- `like_under_terskel`: switch 1 av, switch 2 på
- `over_terskel`: begge av
- Neste hele time: alt som ble kuttet slås på
- `naermer_seg_terskel` / `god_margin`: begge på

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - VVB og panelovn prioritert
use_blueprint:
  path: effektvakt/prioritert_lastkutt.yaml
  input:
    risiko_sensor: sensor.effektvakt_risiko_niva
    switch_high_priority: switch.varmtvannsbereder
    switch_medium_priority: switch.panelovn_stue
    automatikk_switch: switch.effektvakt_automatikk
    max_off_minutes: 60
    min_on_minutes: 5
```

---

## climate_min_temp.yaml

**Hva**: Setter en climate-entitet (panelovn) til min-temp når kutt anbefales, og restorer til lagret temperatur ved neste hele time eller når risiko er borte. En `input_number`-hjelper persisterer temperaturen over HA-restart.

**Passer til**: Panelovner og andre climate-entiteter der du ikke vil slå av helt, men redusere setpunkt.

**Input**:

| Felt                   | Standard                                     | Beskrivelse                                |
| ---------------------- | -------------------------------------------- | ------------------------------------------ |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                        |
| `climate_entity`       | (ingen)                                      | Panelovn eller annen climate               |
| `min_temp`             | 10 °C                                        | Setpunkt under kutt                        |
| `restore_helper`       | (ingen)                                      | `input_number` for å lagre forrige temp    |
| `automatikk_switch`    | (tom)                                        | Hovedbryteren, se over                     |
| `max_off_minutes`      | 60                                           | Absolutt tak hvis timeskiftet aldri kommer |
| `min_on_minutes`       | 5                                            | Minste tid på normal temp før ny senking   |

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

- Sensor `on`: lagre nåværende temp i `input_number`, sett climate til `min_temp`
- Neste hele time: restore til lagret temp
- Sensor `off`: restore til lagret temp
- HA-restart: restore til lagret temp (trigger på `homeassistant.start`)

Temperaturen lagres én gang, før første senking. Varer risikoen i flere timer, er det den brukeren satte som kommer tilbake hver gang, ikke min-temp.

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - Panelovn stue
use_blueprint:
  path: effektvakt/climate_min_temp.yaml
  input:
    binary_sensor_entity: binary_sensor.effektvakt_kutt_ned_anbefalt
    climate_entity: climate.panelovn_stue
    min_temp: 10
    restore_helper: input_number.panelovn_stue_restore_temp
    automatikk_switch: switch.effektvakt_automatikk
    max_off_minutes: 60
    min_on_minutes: 5
```

---

## kun_varsel.yaml

**Hva**: Sender push-notifikasjon når risiko går til `like_under_terskel` eller `over_terskel`. Ingen styring av laster.

**Passer til**: Brukere som vil ta beslutningen selv basert på en notifikasjon.

**Input**:

| Felt                       | Standard                              | Beskrivelse                                                 |
| -------------------------- | ------------------------------------- | ----------------------------------------------------------- |
| `risiko_sensor`            | `sensor.effektvakt_risiko_niva`       | Effektvakt risiko-sensor                                    |
| `kostnad_sensor`           | `sensor.effektvakt_kostnad_neste_trinn` | Kronene i varselet leses herfra                           |
| `tilgjengelig_kutt_sensor` | `sensor.effektvakt_tilgjengelig_kutt` | Forslaget om hva du skal slå av leses herfra                |
| `notify_service`           | `notify`                              | Tjeneste uten `notify.`-prefiks, f.eks. `mobile_app_iphone` |
| `automatikk_switch`        | (tom)                                 | Stopper ikke varselet, men nevnes i teksten når den er av   |
| `dashboard_url`            | (tom)                                 | URL til Lovelace-dashboard, lenkes i notifikasjon           |

**Oppførsel**:

- `like_under_terskel` og `over_terskel`: varsel, med kroner og en handling
- Varselet kommer uansett hvordan hovedbryteren står
- Notifikasjoner køes (mode: queued) for å unngå tap ved rask endring

Kronene er attributtet `kostnad_denne_timen_kr`: hva timen er i ferd med å låse inn på nettleien denne måneden. Har timen ikke flyttet trinnet ennå, sier varselet i stedet hva trinnet over koster. Handlingen er den største av `kutt_kilder` som teller med akkurat nå. Har du ikke konfigurert noen kutt-kilder, blir forslaget generelt.

**Eksempel notifikasjonsinnhold**:

```
Effektvakt: over terskelen
Denne timen låser inn 165 kr ekstra på nettleien denne måneden. Slå av Varmtvannsbereder, den drar 1,8 kW nå.
```

**Eksempel-konfigurasjon**:

```yaml
alias: Effektvakt - Varsel til telefon
use_blueprint:
  path: effektvakt/kun_varsel.yaml
  input:
    risiko_sensor: sensor.effektvakt_risiko_niva
    kostnad_sensor: sensor.effektvakt_kostnad_neste_trinn
    tilgjengelig_kutt_sensor: sensor.effektvakt_tilgjengelig_kutt
    notify_service: mobile_app_min_iphone
    automatikk_switch: switch.effektvakt_automatikk
    dashboard_url: /lovelace/effektvakt
```

---

## Failsafe-garanti

Alle blueprints med laststyring (enkel_lastkutt, prioritert_lastkutt, climate_min_temp) gir lasten tilbake ved timeskiftet, og senest når `max_off_minutes` løper ut. Taket gjelder uavhengig av hva Effektvakt rapporterer.

Løkken som kutter time etter time stopper også av seg selv når sensoren ikke lenger sier `on`. Henger coordinatoren, setter watchdogen sensorene til `unknown` etter 2 minutter, og `unknown` er ikke `on`. VVB-en din blir aldri stående av på ubestemt tid.

Hovedbryteren endrer ikke dette: den hindrer nye kutt, men avbryter aldri et kutt som alt er i gang.
