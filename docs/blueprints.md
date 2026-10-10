# Blueprints

Fire blueprints følger med. Importer den du vil bruke, opprett en automasjon fra den og velg dine entiteter. Å registrere kuttbare laster i Effektvakt oppretter ingen automasjoner. Start gjerne med «Kun varsel» før du aktiverer lastkutt.

## Installer

- [Enkel lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fenkel_lastkutt.yaml): én switch av og på
- [Prioritert lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fprioritert_lastkutt.yaml): to switches i rekkefølge etter hvor nær terskelen timen ligger
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fclimate_min_temp.yaml): panelovn til min-temp med restore
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fmain%2Fdocs%2Fblueprints%2Fkun_varsel.yaml): push-notifikasjon uten styring

Alternativt: kopier `docs/blueprints/` til `/config/blueprints/automation/effektvakt/` og last automasjoner på nytt. YAML-eksemplene under bruker denne mappen. Etter nettimport ligger filen vanligvis under `fredrik-lindseth/`; bruk den faktiske stien i `path`.

## Hovedbryteren

Sett `automatikk_switch` til oppsettets `switch.effektvakt_automatikk` for å hindre nye kutt når bryteren er av. Feltet er valgfritt; uten koblingen lytter automasjonen ikke til bryteren. Bryteren er på som standard og husker lagret av-stilling.

Sensorene regner videre. Avslått automatikk ber om gjeninnkobling ved neste blueprint-vurdering, senest innen ett minutt. Varsel-blueprinten stopper ikke varsler, men nevner at automatikk er av.

## Kuttet slippes ved timeskiftet

Kutt slipper ved neste hele time, `max_off_minutes` eller opphørt kuttbehov, det som kommer først. Standard maks utkobling er 60 minutter og minste påtid fem minutter. Nytt kutt kan skje etter påtiden, også i samme time dersom maksimal utkobling er kortere enn tiden som gjenstår.

Utsatt oppvarming kan lage en ny topp etter gjeninnkobling. Tidsgrensene verner utkoblingen, men planlegger ikke gjenoppvarmingen.

## enkel_lastkutt.yaml

Slår av én switch når kutt anbefales. Velg lasten og grensene etter hva den tåler; lading skal styres via laderens støttede grensesnitt.

| Felt                   | Standard                                     | Beskrivelse                                 |
| ---------------------- | -------------------------------------------- | ------------------------------------------- |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                         |
| `switch_entity`        | (ingen)                                      | Switchen som slås av                        |
| `automatikk_switch`    | (tom)                                        | Hovedbryteren, se over. Tom: hovedbryteren brukes ikke   |
| `max_off_minutes`      | 60                                           | Kortere grense kan slippe før timeskiftet  |
| `min_on_minutes`       | 5                                            | Minste påtid før lasten kan kuttes på nytt  |

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

## prioritert_lastkutt.yaml

Styrer to switches: første ved `like_under_terskel`, begge ved `over_terskel`. Lavere risiko slipper eide kutt.

| Felt                     | Standard                        | Beskrivelse                                |
| ------------------------ | ------------------------------- | ------------------------------------------ |
| `risiko_sensor`          | `sensor.effektvakt_risiko_niva` | Effektvakt risiko-sensor                   |
| `switch_high_priority`   | (ingen)                         | Kuttes først (like under)                  |
| `switch_medium_priority` | (ingen)                         | Kuttes i tillegg (over)                    |
| `automatikk_switch`      | (tom)                           | Hovedbryteren, se over                     |
| `max_off_minutes`        | 60                              | Kortere grense kan slippe før timeskiftet |
| `min_on_minutes`         | 5                               | Minste påtid før nytt kutt                 |

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

## climate_min_temp.yaml

Senker setpunktet til `min_temp` og gjenoppretter lagret temperatur. `restore_helper` er et ubrukt eldre felt. Dette vernet måler ikke temperatur eller varmebehov.

| Felt                   | Standard                                     | Beskrivelse                                |
| ---------------------- | -------------------------------------------- | ------------------------------------------ |
| `binary_sensor_entity` | `binary_sensor.effektvakt_kutt_ned_anbefalt` | Effektvakt-sensoren                        |
| `climate_entity`       | (ingen)                                      | Panelovn eller annen climate               |
| `min_temp`             | 10 °C                                        | Setpunkt under kutt                        |
| `restore_helper`       | (tom)                                        | Valgfritt eldre felt; brukes ikke lenger   |
| `automatikk_switch`    | (tom)                                        | Hovedbryteren, se over                     |
| `max_off_minutes`      | 60                                           | Kortere grense kan slippe før timeskiftet |
| `min_on_minutes`       | 5                                            | Minste tid på normal temp før ny senking   |

```yaml
alias: Effektvakt - Panelovn stue
use_blueprint:
  path: effektvakt/climate_min_temp.yaml
  input:
    binary_sensor_entity: binary_sensor.effektvakt_kutt_ned_anbefalt
    climate_entity: climate.panelovn_stue
    min_temp: 10
    automatikk_switch: switch.effektvakt_automatikk
    max_off_minutes: 60
    min_on_minutes: 5
```

## kun_varsel.yaml

Velg en notify-tjeneste som finnes hos deg; `notify` er bare standardnavnet. Kutt-sensoren finnes bare med målte laster. Uten den blir forslaget generelt.

Sender varsel ved `like_under_terskel` eller `over_terskel`, uten laststyring. Beløpet er timens tariffvirkning, eller prisen på neste trinn hvis timen ennå ikke flytter trinnet. Forslaget velger den største målte lasten som bidrar nå. Varsler kommer også med hovedbryteren av.

| Felt                       | Standard                              | Beskrivelse                                                 |
| -------------------------- | ------------------------------------- | ----------------------------------------------------------- |
| `risiko_sensor`            | `sensor.effektvakt_risiko_niva`       | Effektvakt risiko-sensor                                    |
| `kostnad_sensor`           | `sensor.effektvakt_kostnad_neste_trinn` | Kronene i varselet leses herfra                           |
| `tilgjengelig_kutt_sensor` | `sensor.effektvakt_tilgjengelig_kutt` | Forslaget om hva du skal slå av leses herfra                |
| `notify_service`           | `notify`                              | Tjeneste uten `notify.`-prefiks, f.eks. `mobile_app_iphone` |
| `automatikk_switch`        | (tom)                                 | Stopper ikke varselet, men nevnes i teksten når den er av   |
| `dashboard_url`            | (tom)                                 | URL til Lovelace-dashboard, lenkes i notifikasjon           |

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

## Gjeninnkoblingsvern

Oppdater integrasjonen og importer lastkutt-blueprintene på nytt samtidig. Gamle importerte kopier får ikke nytt vern automatisk.

`effektvakt.styr_last` lagrer originaltilstand, eier og frist før kutt. Gjentatte forespørsler forlenger ikke fristen. Vernet overlever automasjonsreload, entry-unload og HA-omstart. Utilgjengelige aktuatorer prøves igjen ved tilstandsendring og hvert 30. sekund; HA og aktuatoren må være tilgjengelige for å utføre kommandoen.

Minste påtid starter ved bekreftet gjeninnkobling og lagres på disk. En allerede avslått switch eller et allerede lavere setpunkt overtas ikke. Manuelle temperaturendringer under kuttet beholdes. Bare én automasjon kan eie et aktivt kutt per aktuator; bruk én styringsautomasjon per last.
