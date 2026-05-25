# Effektvakt designspec

Dato: 2026-05-25
Status: utkast for review
Repo: `~/dev/hacs-effektvakt/`

## Kongstanke

Prediktiv styring som hindrer at norske strømkunder krysser kapasitetstrinn-grenser i nettleien. Når Effektvakt ser at vi er på vei mot neste trinn for inneværende klokketime, eksponerer den en risiko-trigger som brukerens automasjoner (typisk via blueprint) bruker til å slå av valgte forbrukere midlertidig.

Se `KONGSTANKE.md` i repoet for den fulle motivasjonen.

## Arkitektonisk valg

Etter research på UX-mønstre hos sammenlignbare HACS-integrasjoner (Adaptive Lighting, Battery Notes, EnergyTariff, Powercalc, EMHASS, cheapest-hours-blueprintet) er konklusjonen at integrasjonen ikke skal styre brukerens entiteter direkte. Den eksponerer beslutnings-sensorer og services, og leverer blueprints som brukeren importerer for å koble sine egne switches/climate-entiteter.

Det bryter med KONGSTANKE.md sin opprinnelige skisse om config flow med entitetsvelger for switches. Begrunnelse: økosystemet forventer at controlled targets eies av blueprint/automation, ikke av config flow. Det gir bedre testbarhet, mindre tett kobling, og brukeren beholder kontroll over hva som faktisk slås av.

## Dataflyt

```
[power_sensor W]    ──┐
[energy_sensor kWh] ──┼──> EffektvaktCoordinator (60s tick)
[DSO kapasitetstrinn]─┘     │
                            ├─> projisert_time_snitt_kw
                            ├─> margin_til_neste_trinn_kw
                            ├─> risiko_niva (none/low/medium/high)
                            ├─> kutt_anbefalt_kw
                            └─> topp_3_snitt_denne_maned
                                       │
                                       ├─> sensor.*
                                       ├─> binary_sensor.kutt_ned_anbefalt
                                       └─> services
                                               │
                                               ▼
                              brukerens automasjoner / blueprints
                              (switch.turn_off, climate.set_temperature)
```

## Beregning

Per coordinator-tick (default 60 sek):

```
elapsed_h         = (now.minute + now.second / 60) / 60
remaining_h       = 1.0 - elapsed_h
actual_kwh        = (energy_sensor_now - energy_sensor_at_hour_start)
                    [fallback: integrert p * dt hvis energy_sensor mangler]
current_kw        = power_sensor (W) / 1000
projected_avg     = actual_kwh + current_kw * remaining_h
effective_threshold = max(next_tier_threshold, snitt_av_2_hoyeste_timer_hittil_i_maned)
margin_kw         = effective_threshold - projected_avg
```

### Topp-3-modellen: døgn-topp, ikke time-topp

Norske DSO-er fakturerer etter NVE-modellen: én topp-time per dag, så snitt av de tre høyeste DAGENE i måneden. Strømkalkulator-coordinator implementerer dette via `_daily_max_power: dict[date, DailyMaxEntry]` (én entry per dag, oppdateres ved klokketime-rollover hvis timen ble dagens nye maks). Effektvakt MÅ bruke samme modell, ellers blir hele effective_threshold-resonnementet feil.

Effektvakts coordinator holder derfor:

```python
_daily_max_kw: dict[date, float]   # én topp-time-snitt per dag i inneværende måned
```

`topp_3_snitt_denne_maned = mean(sorted(_daily_max_kw.values(), reverse=True)[:3])`
`topp_2_snitt_denne_maned = mean(sorted(_daily_max_kw.values(), reverse=True)[:2])`

### Hvorfor effective_threshold (topp-3-bevissthet)

Nettleien faktureres etter snittet av topp-3 maks-timer fra **tre ulike dager** per måned. Hvis brukeren allerede har tre dager på 12 kW i et 10-15 kW-trinn, betaler de allerede for 15-trinnet. Å kutte VVB i en time som ligger an til 11 kW gir ingen besparelse hvis dagens forrige maks er lavere, fordi denne dagen ikke kan påvirke faktura-snittet.

`effective_threshold` er det laveste nivået denne timen må holde seg under for å redusere kostnadsbildet:

- **Hvis projisert time-snitt > dagens hittil-maks OG > snittet av topp-2 hittil i måneden**: denne timen kan bli en ny topp-3-dag og påvirker fakturaen. `effective_threshold = next_tier_threshold`.
- **Ellers**: denne timen påvirker ikke fakturaen (enten fordi dagen allerede har en høyere maks, eller fordi den ligger under topp-2-snittet). `effective_threshold = max(next_tier_threshold, topp_2_snitt)`, slik at risiko forblir lav selv ved svingninger.

Effektivt: vi kutter kun når en handling faktisk endrer hvilket trinn brukeren havner på ved måneds-slutt.

### Fallback ved tomt datagrunnlag

Tidlig i måneden har vi ikke nok dager til å beregne `topp_2_snitt`. Policy:

- Hvis `len(_daily_max_kw) < 2`: bruk `effective_threshold = next_tier_threshold`. Konservativt valg når vi mangler kontekst.
- Hvis `len(_daily_max_kw) == 2`: bruk snitt av begge.
- Hvis `len(_daily_max_kw) ≥ 3`: bruk snitt av de to høyeste.

### Energy-sensor-snapshot ved time-rollover

`energy_sensor` har typisk `state_class: total_increasing` (resetter aldri av seg selv, eller bare ved meter-bytte). Coordinator må derfor:

1. Ved oppstart eller første gyldige lesning: lagre `_energy_at_hour_start = current_reading`
2. Per tick: `actual_kwh_this_hour = current_reading - _energy_at_hour_start`
3. Ved klokketime-rollover (detektert via `(hour, utcoffset)`-tuple): arkiver `actual_kwh` til time-historikk, oppdater `_energy_at_hour_start = current_reading`

Negative deltaer (counter reset, meter-bytte) detekteres som i strømkalkulator: bevar forrige `_energy_at_hour_start`, logg advarsel, returner null-bidrag inntil verdien vokser igjen.

### prev_tier_threshold ved under første trinn

Hvis brukerens projisert time-snitt ligger under det laveste konfigurerte trinnet, settes `prev_tier_threshold_kw = None` i sensor-attributter. `next_tier_threshold` blir alltid det laveste trinnet over `projected_avg`.

## Risikoklassifisering

Fire diskrete nivåer, basert på `safety_buffer_kw` (default 1.0):

| Risiko   | Betingelse (på rå margin_kw)               |
| -------- | ------------------------------------------ |
| `none`   | margin > 2 × safety_buffer                 |
| `low`    | safety_buffer < margin ≤ 2 × safety_buffer |
| `medium` | 0 < margin ≤ safety_buffer                 |
| `high`   | margin ≤ 0                                 |

`binary_sensor.kutt_ned_anbefalt` er `on` når **hysteresefull** risiko (se under) ≥ konfigurert `min_risiko_for_kutt` (default `medium`).

## Hysterese (debounce på nedgang)

Effekten kan svinge minutt-til-minutt rundt en terskel. Uten hysterese ville coordinator ha rapportert vekselvis high/medium/high/medium og generert hyppige on/off-pulser på blueprintets binary trigger.

### Policy

- **Oppgang er alltid umiddelbar.** Hvis rå risiko går fra `low → medium`, `medium → high` eller annen oppovergang, rapporterer hysteresefull risiko ny verdi i samme tick. Vi vil aldri bremse en handling som beskytter brukeren.
- **Nedgang krever holdetid.** Når rå risiko går nedover (`high → medium`, `high → low`, `medium → low`, `low → none`, `medium → none`), starter en `risiko_holdetid_minutter`-timer (default 5 min). Hysteresefull risiko blir liggende på det høyere nivået til timeren utløper med rå risiko fortsatt på det lavere nivået.
- **Oscillasjon nullstiller timeren.** Hvis rå risiko går opp igjen mens timeren løper, kanselleres nedgangen. Hysteresefull risiko forblir på topp-nivået.
- **Multi-step nedgang skjer i ett trinn av gangen.** Hvis rå risiko hopper fra `high` til `none`, går hysteresefull til `medium` etter `risiko_holdetid_minutter`, så til `low` etter ytterligere holdetid, så til `none`. Det dempes ut til ro over tid, ikke i én bevegelse.

### Implementasjon (skjelett)

```python
@dataclass
class HystereseState:
    nivå: str                 # nåværende hysteresefulle nivå
    pending_nivå: str | None  # mål-nivået ved nedgang
    pending_since: datetime | None
```

Per tick:

```python
if rå_nivå >= state.nivå:                # oppgang eller likt
    state.nivå = rå_nivå
    state.pending_nivå = None
    state.pending_since = None
elif state.pending_nivå != rå_nivå:      # ny nedgang
    state.pending_nivå = rå_nivå
    state.pending_since = now
elif (now - state.pending_since) >= holdetid:
    state.nivå = nivå_ett_under(state.nivå)
    state.pending_since = now if state.nivå > rå_nivå else None
```

### Konfig-feltet

Tidligere navngivning `min_minutter_mellom_kutt` var misvisende. Feltet styrer holdetid på selve risiko-sensoren, ikke noe brukeren styrer direkte. Endret til `risiko_holdetid_minutter` for å unngå misforståelse.

## Komponenter

```
custom_components/effektvakt/
├── __init__.py           # async_setup_entry, async_unload_entry
├── manifest.json         # platforms: sensor, binary_sensor
├── const.py              # DOMAIN, CONF_*, defaults, RISIKO_*-konstanter
├── dso.py                # KAPASITETSTRINN_PER_DSO (subset-kopi fra strømkalkulator)
├── config_flow.py        # 3-stegs flow + options-flow
├── coordinator.py        # EffektvaktCoordinator
├── sensor.py             # 6 sensorer
├── binary_sensor.py      # 1 binary sensor
├── diagnostics.py        # standard diagnostics-eksport
├── services.yaml         # 2 services
├── strings.json
└── translations/
    ├── en.json
    └── nb.json

docs/
├── blueprints/
│   ├── enkel_lastkutt.yaml
│   ├── prioritert_lastkutt.yaml
│   ├── climate_min_temp.yaml
│   └── kun_varsel.yaml
├── dashboard-eksempel.yaml
└── superpowers/specs/2026-05-25-effektvakt-design.md (denne)

tests/
├── conftest.py
├── fixtures/                       # symlink til ../hacs-strømkalkulator/tests/fixtures/
├── test_coordinator_terskel.py
├── test_coordinator_replay.py      # ekte BKK-fixturer
├── test_config_flow.py
├── test_dso_data.py
└── test_blueprint_yaml_valid.py
```

## Config flow (3 steg)

### Steg 1: DSO

| Felt  | Type                                                                         | Default |
| ----- | ---------------------------------------------------------------------------- | ------- |
| `dso` | SelectSelector (dropdown fra `KAPASITETSTRINN_PER_DSO`, "egendefinert" sist) | `bkk`   |

Hvis "egendefinert": gå til pricing-steg som lar brukeren skrive inn egne trinn (kW-terskel → kr/mnd).

### Steg 2: Sensorer

| Felt            | Type                                               | Påkrevd        |
| --------------- | -------------------------------------------------- | -------------- |
| `power_sensor`  | EntitySelector(domain=sensor, device_class=power)  | ja             |
| `energy_sensor` | EntitySelector(domain=sensor, device_class=energy) | nei (anbefalt) |

#### Validering

- `power_sensor` må returnere finit verdi.
- `power_sensor.unit_of_measurement` må være `W` eller `kW`. Coordinator normaliserer til kW internt. Andre enheter (`VA`, `mW`, etc.) avvises med feilmelding.
- Hvis `energy_sensor` er satt, må den ha `state_class=total_increasing` og `unit_of_measurement=kWh` (eller `Wh`, normaliseres).
- **Sensor-type-deteksjon**: `device_class=power` matcher både instant-power og peak-aggregater (typisk Tibber sin `*_max_power` / `*_max_per_hour`). Hvis brukeren velger en peak-aggregat, blir `projected_avg` overdrevet konservativ og Effektvakt kutter for ofte.

Heuristikk for å fange peak-sensorer:

- `entity_id` matcher mønstre `*_max_power`, `*_peak*`, `*max_per_hour*`, `*_average*`, `*_avg_*`
- `friendly_name` inneholder "max", "peak" eller "average"

Hvis sensoren matcher: config flow viser advarsel:

> "Sensoren ser ut til å rapportere peak- eller snitt-effekt, ikke nåværende effekt. Effektvakt trenger instant-power (oppdaterer hvert ~10 sek). Hvis du bruker Tibber Pulse, velg `sensor.*_power` i stedet for `sensor.*_max_power`. Vil du fortsette likevel?"

Bruker kan haake av en `confirm_peak_sensor`-checkbox for å fortsette. Advarslen lagres i issue registry slik at den dukker opp i HA Repairs hvis brukeren angrer.

### Steg 3: Tuning

| Felt                       | Type                                                  | Default  |
| -------------------------- | ----------------------------------------------------- | -------- |
| `safety_buffer_kw`         | NumberSelector(min=0.1, max=5, step=0.1, mode=slider) | 1.0      |
| `min_risiko_for_kutt`      | SelectSelector ["low", "medium", "high"]              | `medium` |
| `risiko_holdetid_minutter` | NumberSelector(min=1, max=30)                         | 5        |

Alle tre kan endres i options-flow uten å miste data.

### Lagring og unique_id

- `unique_id` på config entry settes til `f"{DOMAIN}_{power_sensor}"`. Det hindrer at samme power-sensor konfigureres to ganger (mønster fra strømkalkulator).
- Persistert state (topp-3-buffer, månedstracking) lagres i `.storage/effektvakt_{entry.entry_id}`. Aldri DSO-id, aldri power_sensor entity_id i filnavnet. Følger incident 001-mønsteret fra strømkalkulator.

## Sensorer

| Entity ID                                    | Unit                   | device_class | state_class | Beskrivelse                                 |
| -------------------------------------------- | ---------------------- | ------------ | ----------- | ------------------------------------------- |
| `sensor.effektvakt_projisert_time_snitt`     | kW                     | power        | measurement | Antatt time-snitt på slutten av timen       |
| `sensor.effektvakt_margin_til_neste_trinn`   | kW                     | power        | measurement | effective_threshold − projected_avg         |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | kW                     | power        | measurement | Snitt av topp-3 maks-timer hittil i måneden |
| `sensor.effektvakt_risiko_niva`              | (none/low/medium/high) | enum         | n/a         | Hysteresefull risikoklassifisering          |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on/off                 | n/a          | n/a         | Trigger for automasjoner                    |

Bevisst demote-t fra eget sensor til attributt:

- `neste_trinn_kw` (statisk per måned, lite verdi som egen entitet) → attributt på `margin_til_neste_trinn`
- `kutt_anbefalt_kw` (triviell `max(0, -margin)`) → attributt på `margin_til_neste_trinn`

Brukeren får da 4 sensorer + 1 binary i sin entitetsliste, ikke 7. Power users som vil ha dem som template-sensorer kan trekke dem fra attributt-tilgang.

### Attributter (felles diagnostikk på alle sensorer)

- `elapsed_minutes_in_hour`: int
- `raw_kwh_this_hour`: float
- `current_power_w`: float
- `next_tier_threshold_kw`: float
- `next_tier_pris_per_maned`: int
- `prev_tier_threshold_kw`: float | null (None hvis brukeren ligger under første trinn)
- `effective_threshold_kw`: float (forklart i Beregning)
- `kutt_anbefalt_kw`: float (max(0, -margin))
- `topp_2_snitt_denne_maned_kw`: float (input til effective_threshold)
- `last_update`: datetime

## Services

```yaml
# services.yaml
set_safety_buffer:
  name: Endre safety buffer
  description: Runtime-justering uten options-flow-reload
  fields:
    kw:
      name: Safety buffer (kW)
      required: true
      selector:
        number:
          min: 0.1
          max: 5
          step: 0.1
          mode: slider

reset_topp_3:
  name: Nullstill topp-3-buffer
  description: Debug-hjelp ved feilmåling
```

Bevisst utelatt: ingen `cut_load`-service. Blueprintet kaller `switch.turn_off` direkte mot sin egen target, slik at API-flaten er tynnere og koblingen lavere.

## Blueprints (4 stk)

Alle lagres som YAML i `docs/blueprints/` og lenkes fra README med My-Home-Assistant-importknapp.

### 1. `enkel_lastkutt.yaml`

- **Bruker**: én VVB eller én billader
- **Trigger**: `binary_sensor.effektvakt_kutt_ned_anbefalt` → on
- **Action**: turn_off på valgt switch
- **Restore**: trigger off → switch.turn_on (eller `restore_after_minutes` hvis brukeren vil)
- **Input-selectors**: switch_entity (selector: target/entity), restore_strategy (selector: select)

### 2. `prioritert_lastkutt.yaml`

- **Bruker**: flere loads i prioritert rekkefølge
- **Trigger**: `sensor.effektvakt_risiko_niva` endrer seg
- **Action**: når risiko stiger, slå av neste switch i prioritert liste; når den synker, slå på reverse
- **Input-selectors**: ordered_switches (selector: target/entity, multiple), max_off_per_switch_minutes (selector: number)

### 3. `climate_min_temp.yaml`

- **Bruker**: panelovner med innebygd termostat
- **Trigger**: binary_sensor → on
- **Action**: sett climate-entitet til min-temp
- **Restore**: trigger off → restore_temperature (lagret før kuttet)
- **Input-selectors**: climates (multiple), min_temp_each (number per climate hvis mulig), restore_to_each

### 4. `kun_varsel.yaml`

- **Bruker**: vil bare bli varslet, styrer manuelt
- **Trigger**: risiko-sensor → medium eller high
- **Action**: notify-tjeneste
- **Input-selectors**: notify_service (selector: service), dashboard_url (selector: text)

### Distribusjon

README har en seksjon:

```markdown
## Blueprints

Klikk for å importere blueprint direkte til ditt HA:

- [Enkel lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=...)
- [Prioritert lastkutt](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=...)
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=...)
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=...)
```

## DSO-data og drift-beskyttelse

`dso.py` inneholder en generert subset-kopi av kapasitetstrinn-data fra strømkalkulator. Bare det Effektvakt trenger: navn, prisområde, kapasitetstrinn (kW-terskel + kr/mnd) og normalisert kapasitetstrinn-format. Ikke energiledd, helligdager, avgiftssone eller fusjonsmigrasjoner.

### Generator-script

`scripts/sync_dso_from_stromkalkulator.py` leser fra `../hacs-strømkalkulator/custom_components/stromkalkulator/dso.py` (relativ sti, krever sibling-checkout) og regenererer `custom_components/effektvakt/dso.py` med en kopi av nødvendige felter, normalisert til ensartet tuple-format `(kw_terskel, kr_per_mnd)`. Filen toppes med en autogenerert-header:

```python
# AUTOGENERATED FROM hacs-strømkalkulator/custom_components/stromkalkulator/dso.py
# Kjør scripts/sync_dso_from_stromkalkulator.py for å regenerere.
# Manuell redigering vil bli overskrevet.
```

### CI-sjekk

En egen workflow-step kjører scriptet og feiler hvis output skiller seg fra committet `dso.py`:

```yaml
- name: Verify DSO data is in sync
  run: |
    git clone --depth 1 https://github.com/fredrik-lindseth/hacs-strømkalkulator ../strømkalkulator
    python scripts/sync_dso_from_stromkalkulator.py
    git diff --exit-code custom_components/effektvakt/dso.py || (
      echo "::error::DSO-data har driftet fra strømkalkulator. Kjør scripts/sync_dso_from_stromkalkulator.py og commit."
      exit 1
    )
```

Det betyr: hvis BKK justerer trinnene sine i strømkalkulator, må Effektvakt synces aktivt før neste PR kan merges. Ingen stille drift.

### Egendefinert DSO

Brukeren kan velge "egendefinert" og skrive inn egne trinn i pricing-steget. Disse lagres i config entry, ikke i `dso.py`, og påvirkes ikke av sync-scriptet.

## Replay-test

Fixturene fra strømkalkulator har time-aggregat (`kwh` + `p_max_w` per time), ingen minutt-data. Replay-testen kan derfor IKKE måle "tid til deteksjon i minutter". Hvis vi senere skaffer minutt-data fra Tibber-API, kan vi utvide testen.

`test_coordinator_replay.py` symlinker `tests/fixtures/ → ../hacs-strømkalkulator/tests/fixtures/` og kjører to varianter:

### Variant A: Kontrafaktisk besparelses-test (primær)

NB: dette er ikke en prediksjonskvalitets-test. Variant A antar at Effektvakt rakk å reagere i tide og måler hvor mye brukeren ville spart. Selve treffraten (oppdager Effektvakt risikoen i tide?) krever ekte minutt-data og testes ikke her.

For hver time i fixturen:

1. Sett `actual_kwh = fixtur.kwh` (som om vi var helt på slutten av timen, `elapsed_h = 1.0`)
2. Sett `current_kw = 0` (timen er ferdig)
3. La coordinator akkumulere `daily_max_kw` og topp-3 over måneden via NVE-modellen (én topp-time per dag)

Kjør så en kontrafaktisk:

1. For hver dag hvor en time ville krysset effective_threshold (`risiko ≥ medium` hadde Effektvakt sett dette real-time): anta blueprint-handling reduserer den timens kwh med 0.5 kWh (én VVB gir -1 kW i 30 min hvis handling kommer på plass halvveis i timen).
2. Regn ny `daily_max_kw` for den dagen (timen kan fortsatt være dagens høyeste, men med lavere verdi).
3. Beregn post-styring topp-3-snitt over måneden.

Konkrete assertioner:

- **Ingen falsk-positiv-styring**: Effektvakt skal IKKE ha forsøkt kutt i timer hvor fixtur-kwh ≤ snitt-av-topp-2-DAGER-hittil (verifiserer at effective_threshold-logikken virker mot døgn-topp-modellen).
- **Skadebegrensning, gitt prediksjonstreff**: Over 5 BKK-måneder (des 2025 → apr 2026) skal post-styring topp-3-snitt være ≥ 0.3 kW lavere enn rå topp-3-snitt i ≥ 4 av 5 måneder.
- **Trinn-bevaring**: I minst 2 av 5 måneder skal post-styring topp-3-snitt havne i et lavere kapasitetstrinn enn rå topp-3-snitt. Det er det som faktisk gir kroner spart, ikke små reduksjoner innenfor samme trinn.

### Variant B: Syntetisk minutt-replay (sekundær)

Generer flat minutt-profil med kjent total-kwh:

- For hver time: 60 ticks med `current_kw = fixtur.kwh` (konstant effekt over timen)
- Peak settes til `p_max_w / 1000` i ett tilfeldig minutt (best-effort representasjon)

Eksplisitt scope: tester at coordinator-logikken oppdager risiko over tid uten oscillasjon, ikke minutt-presisjon. Antagelser dokumenteres i test-filens docstring.

Assertioner:

- Risikoklassifiseringen kommer ikke til `high` i timer hvor fixtur-kwh er > 3 kW under nest-høyeste-trinn (sanity: vi over-reagerer ikke).
- Hysterese-sensor er stabil (ingen mer enn 2 toggles per time i variant B).

### Tuning

Replay-resultatene styrer default-verdiene for `safety_buffer_kw` og `risiko_holdetid_minutter`. Konkret prosess (utenfor sesjons-scope): kjør testen med ulike parameter-verdier, plot post-styring topp-3 vs. falsk-positiv-rate, velg defaults som maksimerer (real_reduction - 0.5 × false_positives).

## Feilhåndtering og failsafe

Effektvakt kan i prinsippet etterlate brukeren med en VVB som ble slått av kl. 14:32 og aldri kommer tilbake hvis coordinator henger eller HA restarter. Spec'en gjør derfor failsafe til et eksplisitt designkrav, ikke noe blueprintet "burde" håndtere.

### Sensor unavailable

Returner siste kjente verdi i opptil 2 minutter, deretter `unknown`. Risiko-sensor blir `unknown` (ikke `none`). Blueprints MÅ behandle `unknown` som "ikke kutt" og slå PÅ igjen alt som var slått av.

### Watchdog mot coordinator-crash

Coordinator skriver `_last_successful_update` til `hass.data[DOMAIN]` ved hver vellykket tick. En egen `async_track_time_interval`-callback (uavhengig av coordinator) sjekker hvert minutt:

```python
if (now - last_successful_update) > timedelta(minutes=2):
    # coordinator henger eller har feilet
    set_all_sensors_unknown()
```

Det sikrer at "sensor blir unknown ved coordinator-død" virker selv om coordinator-loopen selv står stille.

### Restore-tidsfrist i lastkutt-blueprints

Lastkutt-blueprints (`enkel_lastkutt`, `prioritert_lastkutt`, `climate_min_temp`) MÅ inneholde `max_off_minutes`-input. `kun_varsel` har ingen handling å reversere og er unntatt.

Skjelett for lastkutt-blueprints:

```yaml
input:
  max_off_minutes:
    name: Maks minutter slått av før tving-on
    default: 30
    selector:
      number: {min: 1, max: 240}

trigger:
  - platform: state
    entity_id: binary_sensor.effektvakt_kutt_ned_anbefalt
    to: "on"

action:
  - service: switch.turn_off
    target: !input switch_entity
  - delay: minutes: !input max_off_minutes
  - service: switch.turn_on        # tving on uansett state på binary_sensor
    target: !input switch_entity
```

Det betyr at selv om coordinator dør og `binary_sensor.kutt_ned_anbefalt` aldri går tilbake til `off`, blir lasten tvunget på etter `max_off_minutes`. Default 30 min er trygt for VVB (vannet rekker ikke kjøles ut) og kort nok til at billader-økten ikke hakkes opp.

### Climate-restore-temp må persisteres

Climate-blueprintet (`climate_min_temp.yaml`) lagrer brukerens forrige temperatur før det settes min-temp. Lagring i blueprint-state alene forsvinner ved HA-restart. Climate-blueprintet bruker derfor en input_number-hjelper som brukeren oppretter (skrives eksplisitt i README), og restore skjer ved enten `binary_sensor.kutt_ned_anbefalt → off` ELLER `max_off_minutes` ELLER `homeassistant.start`-trigger.

### Andre tilfeller

- **Energy_sensor counter reset**: detekter negative deltas, behandle som null-bidrag, logg warning. Samme mønster som strømkalkulator.
- **DST-overgang**: time-bucket nullstilles ved klokketime-overgang basert på `(hour, utcoffset)`-tuple. Følger strømkalkulator-mønsteret.
- **Coordinator-crash uten reload**: HA håndterer reload automatisk. Topp-3-buffer + hour-historikk persisteres til `.storage/effektvakt_{entry_id}` slik at månedlig tracking overlever restart.
- **Brukeren overskrider trinnet likevel**: ikke unormalt. Logg info, ikke warning. Topp-3-sensoren reflekterer faktum.

## Persistering

Skrives til `.storage/effektvakt_{entry.entry_id}` ved hver klokketime-rollover og ved måneds-rollover. Følger NVE-modellen: én topp-time per dag, ikke full time-historikk.

```json
{
  "version": 1,
  "data": {
    "current_month": "2026-05",
    "daily_max_kw": {
      "2026-05-01": 5.4,
      "2026-05-02": 7.2,
      "2026-05-25": 9.1
    },
    "current_hour_kwh": 2.34,
    "current_hour_started_at": "2026-05-25T14:00:00+02:00",
    "energy_at_hour_start": 124523.105,
    "previous_month_top_3_snitt_kw": 9.2,
    "previous_month_name": "2026-04",
    "hysterese_state": {"nivå": "low", "pending_nivå": null, "pending_since": null}
  }
}
```

- `daily_max_kw` har én entry per dag i inneværende måned. Oppdateres ved klokketime-rollover: hvis ferdig-time-snitt > dagens nåværende verdi, erstatt.
- `current_hour_kwh` lar en restart midt i timen plukke opp akkumulert kwh og fortsette beregningen.
- `previous_month_top_3_snitt_kw` arkiveres ved måneds-rollover for fakturaverifisering-sensor.
- Ved måneds-rollover: regn topp-3-snitt av forrige måneds `daily_max_kw`, arkiver verdien, tøm `daily_max_kw` for ny måned. Skjer aldri midt i en åpen time, kun ved time-rollover ETTER at klokketime-skiftet har passert ny måned.

### Brukeren oppgraderer / endrer DSO-trinn

To distinkte tilfeller:

1. **Brukeren bytter DSO eller oppgraderer hovedsikring**: håndteres via options-flow (steg 1: DSO-velger, steg 3: tuning). Ved bytte signaliseres options-update-listener i `__init__.py`, og coordinator reloades. `hour_history` beholdes (ren forbruks-historikk er DSO-uavhengig), men `effective_threshold` regnes på ny mot nye trinn-grenser ved første tick.

2. **Brukeren har de facto vært i et høyere trinn lenge (uten å ha endret config)**: dekkes automatisk av `effective_threshold`-logikken. Hvis topp-2-snitt er 10.5 kW i et 10-15 kW-trinn, blir effective_threshold = 15, og Effektvakt beskytter neste-trinns-overskridelse, ikke en grense brukeren allerede har krysset. Ingen manuell handling kreves.

## Testing

| Test                           | Hva den dekker                                                    |
| ------------------------------ | ----------------------------------------------------------------- |
| `test_coordinator_terskel.py`  | Beregning av margin/risiko ved kjente input                       |
| `test_coordinator_replay.py`   | Replay mot ekte BKK-fixturer                                      |
| `test_config_flow.py`          | Validering av sensorer, options-flow                              |
| `test_dso_data.py`             | Sanity-sjekk på alle DSO-er (terskler stigende, prisene stigende) |
| `test_hysteresis.py`           | Hysterese-logikk                                                  |
| `test_blueprint_yaml_valid.py` | Alle blueprints validerer mot HA-blueprint-schema                 |

CI-mål: minst 80 % linjedekning på coordinator + 95 % på risiko/hysterese-funksjoner.

## Tooling

Kopiert direkte fra strømkalkulator:

- `pyproject.toml` (ruff, mypy, vulture, pytest)
- `.pre-commit-config.yaml`
- `.github/workflows/{ci,validate,release}.yml`
- `vulture_whitelist.py`
- `.gitignore`
- `LICENSE` (MIT)
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`

## Dashboard-eksempel

`docs/dashboard-eksempel.yaml` er en kopiérbar Lovelace-YAML som viser:

- Gauge: `margin_til_neste_trinn` (rød < 0, gul < safety_buffer, grønn > 2× buffer)
- Entities-kort: alle sensorer
- Bar-chart: topp-3 denne måneden
- Tankart: risiko_niva med fargekoding

Brukere kopierer YAML inn i sin egen dashboard, ingen custom cards trengs.

## Tick-frekvens og kjente begrensninger

### Adaptiv tick

Coordinator bruker adaptiv tick basert på hysteresefull risiko:

- `none` eller `low`: 60s tick
- `medium`: 30s tick
- `high`: 15s tick

Implementert via at coordinator selv kaller `async_request_refresh()` igjen etter handling, ev. via `async_set_update_interval` ved nivå-endring. Reduserer worst-case stale data nær margingrensen fra 50s til 12s ved kritisk nivå.

### Sen-i-timen-blindspot

Hvis brukeren slår på en stor last kl. 18:58, har coordinator kun 1-2 ticks igjen før timen er over. `current_kw × remaining_h`-leddet går mot 0, så projisert snitt vil ikke reflektere den nye lasten før neste tick (som da er etter rollover). Worst-case: den timen kan bli ny topp-3-dag uten at Effektvakt rakk å reagere.

Dette er en fundamental begrensning av 60s polling-frekvens og kan ikke unngås uten direkte event-trigger på power-sensor-endring. Aksepteres som kjent svakhet. Brukere som vil ha tettere oppfølging må bygge automasjon utenfor Effektvakt som trigger på power-sensor og kaller en manuell sjekk.

### Andre tilfeller

- **DST-overgang (29.03 og 27.10)**: time-bucket nullstilles ved `(hour, utcoffset)`-tuple endring, ikke kun hour. Spesielt høst-DST gir to 02-timer på rad: `current_hour == prev_hour` men `utcoffset` skifter +02:00 → +01:00. Følg samme mønster som strømkalkulator coordinator.py:557-580.

## Realistiske kuttmengder (post-research 2026-05-25)

Etter at v0.1.0 ble bygget, ble det gjort research på faktiske VVB-egenskaper og duty cycle. Funn (se kilder under):

- Norsk standard VVB (OSO Saga): 2 kW element, duty cycle 10-15% i hvile
- Et 30-min av-vindu uten statussensor treffer "element på" bare ~15% av tiden
- **Blind VVB-kutt**: forventet 0.15 kWh per event (duty-cycle-vektet)
- **VVB med statussensor**: 1.0 kWh per event (2 kW i 30 min, garantert treff)
- **VVB + billader-pause**: opp til 2.5 kWh per event

Legionella er IKKE et reelt problem ved 15-60 min av-perioder så lenge tanken holder ≥ 60°C ved start. FHI har ingen restriksjoner mot prisstyring i private boliger.

### Empirisk replay-resultat (5 BKK-måneder, des 2025 - apr 2026)

| Scenario | Maks månedlig forbedring | Trinn-bevaring |
|---|---|---|
| Blind VVB (0.15 kWh) | +0.15 kW (mars) | Aldri |
| VVB med status (1.0 kWh) | +0.67 kW (mars) | Aldri |
| VVB + billader (2.5 kWh) | +0.67 kW (mars, capped) | Aldri |

**Innsikt**: Effektvakt har verdi i å hindre OPPGRADERING til neste trinn, ikke nedgradering. Når topp-3-snitt allerede ligger godt inne i et trinn (som vintermåneder i 5-10 kW-trinnet), gir kutt ingen kroner spart. Mars-måneden viser at 0.67 kW reduksjon er mulig hvis det skjer nær en trinngrense.

### Anbefalinger til v0.2

Coordinator bør konfigureres med eksplisitt kutt-modell:

1. **Add CONF_KUTT_STRATEGI**: enum `blind | with_vvb_status | with_billader`
2. **Add CONF_VVB_POWER_SENSOR**: optional sensor som rapporterer VVB-effekt i sanntid. Når satt: anbefal kun kutt når sensoren viser > 1000 W (elementet varmer).
3. **Add CONF_BILLADER_ENTITY**: optional switch som kan pauses for ekstra ~3.6 kW headroom.
4. **Coordinator-output**: nytt felt `realistisk_kutt_kw` som reflekterer brukerens kutt-konfigurasjon.

Disse endringene er deferred til v0.2 fordi v0.1.0 er kjøreklar i grunnform.

### Kilder

- [FHI - Legionellaveilederen](https://www.fhi.no/ss/veiledere/legionellaveilederen/temakapitler/risikokartlegging-og-forebyggende-til/)
- [Energy Vanguard - Water Heater Cycling and Legionella](https://www.energyvanguard.com/blog/will-your-water-heater-give-you-legionnaires-disease/)
- [ByggeBolig - Tidsstyring på varmtvannsbereder](https://byggebolig.no/el-varmtvannsbereder/tidsstyring-pa-varmtvannsbereder)
- [OSO Hotwater Saga Standard](https://osohotwater.no/product/varmtvannsbereder-saga-standard/)
- [Tu.no - Hvordan styre effektforbruket](https://www.tu.no/artikler/ny-nettleie-hvordan-styre-effektforbruket/515299)

## Deferred (settes opp senere)

- **Auto-detect av strømkalkulator-sensorer**: utenfor scope nå (brukeren valgte full uavhengighet via egen DSO-liste).
- **Event-trigger på power-sensor-endring** for å fjerne sen-i-timen-blindspot. Krever HA-state-tracker som er ortogonalt fra coordinator-modellen.
- **v0.2 kutt-strategi-konfig**: CONF_KUTT_STRATEGI + CONF_VVB_POWER_SENSOR + CONF_BILLADER_ENTITY (se Realistiske kuttmengder).

## Bevisst utenfor scope

Direkte fra KONGSTANKE.md:

- VVB-styring basert på spotpris alene (cheapest-hours-blueprintets domene)
- Batteri-arbitrage (EMHASS sitt domene)
- Solcelle-prediksjon
- Last-styring uten kapasitetstrinn-kontekst
- Erstatning for generell HA-automasjon-DSL

## Implementasjonsrekkefølge

Korrigert etter review: `config_flow.py` refererer til `CONF_*`-konstanter fra `const.py`, så `const.py` MÅ være ferdig før `config_flow` kan skrives. `dso.py` må også eksistere før config_flow kan bygge DSO-dropdown.

1. **Skjelett**: `__init__.py` (stub), `const.py`, `dso.py` (kopi via sync-script), `manifest.json` (oppdater platforms)
2. **Tooling** (parallelt med 1): `pyproject.toml`, `.pre-commit-config.yaml`, CI-workflows, `scripts/sync_dso_from_stromkalkulator.py`
3. **Config flow**: `config_flow.py` (3 steg + options + power-sensor-heuristikk + advarsel)
4. **Coordinator**: `coordinator.py` med beregning, hysterese, persistering, watchdog
5. **Sensorer** (parallelt med 4): `sensor.py` + `binary_sensor.py`
6. **i18n**: `strings.json` + `translations/{en,nb}.json`
7. **Tester**: unit-tester først (terskel, hysterese, dso-data, config-flow), replay sist
8. **Blueprints** (parallelt med 9): 4 blueprints med max_off_minutes + YAML-validerings-test
9. **Docs**: README, dashboard-eksempel, skjermbilder
10. **Release**: CHANGELOG + initial 0.1.0-tag

Avhengigheter:

- Steg 1 må fullføres før 3.
- Steg 1 og 2 kan kjøre parallelt.
- Steg 4 venter på 1.
- Steg 5 og 6 kan kjøre parallelt med 4 (sensor-skjelett kan bygges mot coordinator-interface).
- Steg 7 venter på 4 og 5.
- Steg 8 og 9 kan kjøre parallelt etter 6.

## Endringer etter review (runde 2)

1. **Døgn-topp, ikke time-topp**: Kritisk fiks. NVE-modellen er én topp-time per dag, så snitt av tre høyeste DAGENE. Strømkalkulator implementerer det via `_daily_max_power: dict[date, ...]`. Effektvakts coordinator bruker nå `_daily_max_kw: dict[date, float]`, og `effective_threshold` bygger på topp-2-DAGER, ikke topp-2-timer.
2. **Persistering forenklet**: `daily_max_kw` (én entry per dag) i stedet for full `hour_history`. Mindre minne og lagring, samsvarer med NVE-modellen.
3. **Fallback ved tomt datagrunnlag**: når `len(daily_max_kw) < 2`, faller `effective_threshold` tilbake til ren `next_tier_threshold`. Konservativt valg første dager i måneden.
4. **`kun_varsel.yaml` unntatt `max_off_minutes`**: motsetning fra forrige spec rettet. Bare lastkutt-blueprints har failsafe-input.
5. **Power-sensor unit-validering**: avvis hvis ikke W eller kW. Energy-sensor: avvis hvis ikke kWh eller Wh.
6. **Adaptiv tick-frekvens flyttet til kjerne**: 60/30/15s basert på risiko-nivå. Tidligere "deferred", nå spesifisert som påkrevd.
7. **Sen-i-timen-blindspot dokumentert**: kjent begrensning av 60s polling. Hvis bruker slår på stor last 18:58, kan timen bli ny topp-3-dag før Effektvakt rakk å reagere.
8. **DST-overgang eksplisitt referert** til strømkalkulator coordinator.py:557-580 som mønster.
9. **Replay variant A omformulert**: kontrafaktisk besparelses-test, ikke prediksjonskvalitets-test. Egen assertion for trinn-bevaring (post-styring snitt havner i lavere kapasitetstrinn).

## Endringer etter review (runde 1)

Følgende ble lagt til etter første review:

1. **Topp-3-bevissthet**: `effective_threshold = max(next_tier, snitt_av_topp_2_hittil)` for å unngå falsk-positive kutt andre halvdel av måneden.
2. **Hysterese utvidet**: alle nedovergangs-overganger, oscillasjon nullstiller timer, multi-step nedgang skjer trinn-for-trinn. `min_minutter_mellom_kutt` omdøpt til `risiko_holdetid_minutter`.
3. **Failsafe**: watchdog-callback uavhengig av coordinator, max_off_minutes som påkrevd input i hver blueprint, climate-restore-temp persisteres via input_number-hjelper.
4. **DSO-drift**: `scripts/sync_dso_from_stromkalkulator.py` + CI-diff-sjekk, ikke deferred.
5. **Power-sensor-validering**: heuristikk på navn (`*_max_power`, `*_peak*`, etc.) + advarsel + opt-in-checkbox.
6. **Sensor-katalog redusert**: `neste_trinn_kw` + `kutt_anbefalt_kw` demote-t til attributter. 4 sensorer + 1 binary i stedet for 6 + 1.
7. **Energy-snapshot eksplisitt**: `_energy_at_hour_start` oppdateres ved time-rollover.
8. **Replay-strategi realistisk**: endepunkts-replay (variant A) som hoved-test, syntetisk minutt-replay (variant B) som sekundær. Eksplisitt at fixturene ikke har minutt-data. Konkret terskel: post-styring topp-3 ≥ 0.3 kW lavere i ≥ 4 av 5 måneder.
9. **Persistering spesifisert**: full `hour_history` for inneværende + forrige måned, ikke bare topp-3-snitt.
10. **DSO-endring**: håndtering ved options-flow vs. de facto-oppgradering klargjort.
11. **Implementasjonsrekkefølge**: `const.py` før `config_flow.py`, parallelliseringer korrigert.
