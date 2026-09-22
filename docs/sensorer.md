# Sensorer

Effektvakt oppretter ett device med 6 sensorer, 1 binary sensor og 1 switch. Sensorene deler et sett felles attributter.

## Oversikt

| Sensor                                       | Enhet  | State class |
| -------------------------------------------- | ------ | ----------- |
| `sensor.effektvakt_projisert_time_snitt`     | kW     | measurement |
| `sensor.effektvakt_margin_til_neste_trinn`   | kW     | measurement |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | kW     | measurement |
| `sensor.effektvakt_risiko_niva`              | enum   | -           |
| `sensor.effektvakt_tilgjengelig_kutt`        | kW     | measurement |
| `sensor.effektvakt_kostnad_neste_trinn`      | kr/mnd | measurement |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on/off | -           |
| `switch.effektvakt_automatikk`               | on/off | -           |

## Navn og entitets-id

Navnene entitetene vises med kommer fra `strings.json` og `translations/`, og følger språket i Home Assistant. Entitets-id-ene gjør ikke det: de settes eksplisitt i `sensor.py`, `binary_sensor.py` og `switch.py`, slik at de står likt på alle språk. Lot vi HA utlede dem, ville en engelsk installasjon fått `sensor.effektvakt_projected_hourly_average`, og både tabellen over, blueprintene og kortet ville pekt på en id som ikke fantes.

Skal du legge til en entitet: unique_id og entity_id skal ha samme nøkkel som `translation_key`, og alle tre oversettelsesfilene må få en `entity`-oppføring. `tests/test_translations.py` fanger en glemt fil.

---

## `sensor.effektvakt_projisert_time_snitt`

**Hva**: Forventet time-snitt i kW ved slutten av inneværende klokketime, gitt at nåværende effekt holder seg til time-slutt.

**Enhet**: kW

**Oppdateres**: Hvert 60 sekund med margin til terskelen, 30 sekund like under den, 15 sekund over.

**Pålitelighet**: God etter de første par minuttene av timen. Tidlig i timen (0-5 minutter) dominerer `current_kw`-leddet fullstendig, siden lite energi er registrert ennå. Mangler energy-sensor, estimeres `actual_kwh_this_hour` fra effekt \* tid, noe som kan gi avvik.

**Formel**: Se [beregninger.md](beregninger.md).

---

## `sensor.effektvakt_margin_til_neste_trinn`

**Hva**: Antall kW mellom projisert time-snitt og `effective_threshold_kw`. Positiv verdi betyr at du er under terskelen. Negativ verdi betyr at terskelen allerede er overskredet denne timen.

**Enhet**: kW

**Oppdateres**: Samme frekvens som projisert time-snitt.

**Pålitelighet**: Avhenger av projisert time-snitt. Marginen er estimert og mer usikker tidlig i timen. Topp-3-justeringen gjøres via `effective_threshold_kw`, som er høyere enn `next_tier_threshold_kw` hvis topp-2-snittet fra tidligere dager allerede overstiger terskel-kW.

---

## `sensor.effektvakt_topp_3_snitt_denne_maned`

**Hva**: Snitt av de tre høyeste time-forbrukene (kWh per time, ikke kW per øyeblikk) fra ulike dager hittil denne måneden. Dette er grunnlaget for kapasitetstrinn-fakturering (NVE-modellen).

**Enhet**: kW

**Oppdateres**: Hver gang en time fullføres, dvs. ved time-skifte.

**Pålitelighet**: Upålitelig de første 1-2 dagene av måneden. Med bare én dag logget returneres snittet av den ene dagen. Med to eller flere dager er verdien meningsfull. Tilbakestilles automatisk ved månedsskifte.

**Merk**: Sensoren viser 0,0 kW helt i starten av en ny måned (ingen dager logget ennå). Det er korrekt oppførsel.

---

## `sensor.effektvakt_risiko_niva`

**Hva**: Hvor nær neste kapasitetstrinn timen ligger an til å komme, med hysterese. Grunnlaget er margin til neste trinn og konfigurert sikkerhetsbuffer.

**Enhet**: enum

**Verdier**:

| Nivå                  | Vises som             | Betingelse                                        |
| --------------------- | --------------------- | ------------------------------------------------- |
| `god_margin`          | God margin            | Margin > 2 × sikkerhetsbuffer                     |
| `naermer_seg_terskel` | Nærmer seg terskelen  | Sikkerhetsbuffer < margin <= 2 × sikkerhetsbuffer |
| `like_under_terskel`  | Like under terskelen  | 0 < margin <= sikkerhetsbuffer                    |
| `over_terskel`        | Over terskelen        | Margin <= 0 (terskelen er overskredet)            |

Tilstanden er verdien i venstre kolonne. Det er den automasjoner, maler og `dcat`-vennlige logger sammenligner mot. Teksten i midten er oversettelsen HA viser, på norsk og engelsk.

Verdiene het `none`, `low`, `medium` og `high` fram til september 2026. Gamle verdier lagret i config entryen eller i hysterese-tilstanden oversettes automatisk, men historikk i recorder står igjen med de gamle navnene, så en graf over månedsskiftet ser delt ut.

**Hysterese**: Oppgang til et mer alvorlig nivå skjer umiddelbart. Nedgang skjer ett trinn av gangen og krever at det lavere nivået holder seg i `risiko_holdetid_minutter` (standard 5 min) før det bekreftes.

**Oppdateres**: Samme frekvens som projisert time-snitt.

---

## `sensor.effektvakt_tilgjengelig_kutt`

**Hva**: Estimert kutt-kapasitet i kW basert på valgt strategi og sensor-avlesninger.

**Enhet**: kW

**Avhenger av strategi**:

- `blind`: alltid 0,3 kW
- `vvb_status`: faktisk VVB-effekt hvis VVB er aktiv (over 1000 W terskel), ellers 0,0 kW
- `vvb_pluss_ekstra`: VVB-effekt pluss sum av ekstra-sensorer over 100 W terskel

**Merk**: Denne sensoren sier ingenting om risiko. Den er en hjelpe-sensor for blueprints og dashboards som vil vise "vi kan kutte X kW nå".

### Attributter

I tillegg til fellesattributtene lenger nede:

| Attributt              | Enhet | Beskrivelse                                                    |
| ---------------------- | ----- | -------------------------------------------------------------- |
| `kutt_strategi`        | str   | Aktiv strategi: `blind`, `vvb_status` eller `vvb_pluss_ekstra` |
| `vvb_power_w`          | W     | VVB-effekten slik den leses nå. `null` uten VVB-sensor         |
| `ekstra_power_w_total` | W     | Sum av ekstra-sensorene. `null` når ingen av dem har en verdi  |
| `kutt_kilder`          | liste | Én oppføring per konfigurert kilde, se under                   |

### `kutt_kilder`

Tilstanden er en sum, og `kutt_kilder` er postene den er summen av. Hver konfigurert kilde har én oppføring:

| Nøkkel       | Beskrivelse                                                                        |
| ------------ | ---------------------------------------------------------------------------------- |
| `entity_id`  | Sensoren kilden leses fra                                                          |
| `navn`       | HA sitt `friendly_name`. `null` hvis entiteten ikke finnes ennå                    |
| `effekt_w`   | Effekten akkurat nå. `null` når sensoren er `unavailable`, `unknown` eller ulesbar |
| `teller_med` | Om kilden faktisk bidrar til tilstanden akkurat nå                                 |
| `rolle`      | `vvb` eller `ekstra`. Rollen bestemmer terskelen                                   |
| `terskel_w`  | Terskelen som gjelder for rollen: 1000 W for `vvb`, 100 W for `ekstra`             |

```yaml
kutt_kilder:
  - entity_id: sensor.vvb_power
    navn: Varmtvannsbereder
    effekt_w: 1800.0
    teller_med: true
    rolle: vvb
    terskel_w: 1000.0
  - entity_id: sensor.varmekabler_badet_electric_consumption_w
    navn: Varmekabler badet
    effekt_w: 12.0
    teller_med: false
    rolle: ekstra
    terskel_w: 100.0
```

Alle konfigurerte kilder er med, også de som ikke teller nå. Forskjellen mellom "finnes ikke" og "teller ikke nå" er nettopp det som er verdt å se på et dashboard. En kilde får `teller_med: false` når strategien ikke bruker rollen, når sensoren er utilgjengelig, eller når effekten ligger på eller under terskelen.

`effekt_w: null` er ikke det samme som `0`. Null watt betyr at lasten står stille, `null` betyr at vi ikke vet.

Summen av `effekt_w` for oppføringene med `teller_med: true` er tilstanden til sensoren, i W mot kW. Unntaket er `blind`, der tilstanden er duty cycle-antagelsen på 0,3 kW og ingen kilder teller med.

---

## `sensor.effektvakt_kostnad_neste_trinn`

**Hva**: Hva det koster per måned å havne på neste kapasitetstrinn. Tilstanden er månedsprisen for neste trinn minus månedsprisen for trinnet måneden ligger an til, altså kronene som står på spill hvis topp-3-snittet krysser terskelen over. Ligger du på BKKs 10 kW-trinn til 415 kr, og neste er 15 kW til 600 kr, viser sensoren 185.

**Enhet**: kr/mnd. Ingen device_class: `MONETARY` krever ISO-valutakode som enhet og en total-state_class, og satser hører hjemme i kr/mnd. Samme regel som i strømkalkulator. State class er `measurement`, så tallet kan grafes over tid.

**Trinnet du ligger an til** er trinnet til `topp_3_projisert_kw`, ikke til topp-3-snittet slik det står nå. Det er topp-3-snittet der dagens dagsmaks er byttet ut med det høyeste av dagens maks så langt og projisert time-snitt nå. Prisen er flat månedspris uten pro rata, så sensoren er like skarp den 1. som den 28.

**Oppdateres**: Samme frekvens som projisert time-snitt.

**Pålitelighet**: Tidlig i måneden deler topp-3-snittet på antall dager, ikke alltid på tre. To dager på 12 kW gir topp-3 lik 12, og en rolig tredje dag drar snittet ned til 8,17. Sensoren arver det, så den kan vise et lavere trinn etter hvert som måneden går. Det pessimistiske utslaget er riktig retning for et varsel, men ikke les tallet som en fasit de første dagene.

**Ukjent nettselskap**: Uten kapasitetstrinn er tilstanden `unknown` og alle kostnadsattributtene `None`.

### Attributter

I tillegg til fellesattributtene lenger nede:

| Attributt                   | Enhet  | Beskrivelse                                                                             |
| --------------------------- | ------ | --------------------------------------------------------------------------------------- |
| `trinn_na_kr`               | kr/mnd | Månedsprisen for trinnet måneden ligger an til                                          |
| `trinn_na_ovre_grense_kw`   | kW     | Øvre terskel for det trinnet. `null` på øverste trinn, som ikke har noen øvre grense    |
| `trinn_neste_kr`            | kr/mnd | Månedsprisen for trinnet over. `null` når du alt er på øverste trinn                    |
| `besparelse_trinn_under_kr` | kr/mnd | Hva du sparer på å komme ned et trinn. 0 på laveste trinn                               |
| `trinn_under_oppnaelig`     | bool   | Om trinnet under fortsatt er innen rekkevidde denne måneden                             |
| `kostnad_denne_timen_kr`    | kr/mnd | Kronene den inneværende timen er i ferd med å låse inn. 0 når timen ikke flytter noe    |
| `topp_3_projisert_kw`       | kW     | Topp-3-snittet med dagens projeksjon regnet inn. Dette er trinnet måneden ligger an til |
| `minste_mulige_topp_3_kw`   | kW     | Nedre skranke: sum av inntil tre høyeste låste dagsmaks delt på 3                       |
| `kapasitetstrinn`           | liste  | Hele trinn-tabellen som `[kW, kr]`-par                                                  |

`kapasitetstrinn` er tabellen et dashboard trenger for å tegne skalaen selv. Øverste terskel er uendelig internt, og `inf` er ugyldig JSON og knekker både recorder og websocket, så den sendes som `null`:

```yaml
kapasitetstrinn:
  - [2.0, 155]
  - [5.0, 250]
  - [10.0, 415]
  - [15.0, 600]
  - [null, 6900]
```

`trinn_under_oppnaelig` sammenligner `minste_mulige_topp_3_kw` mot terskelen til trinnet under. Skranken teller bare dagsmaks som alt er låst inn, ikke den inneværende timen, nettopp fordi den timen fortsatt kan kuttes. En enkelt dag på 7 kW gir 2,33, og trinnet under er da oppnåelig. Tre dager på 6, 7 og 8 gir 7,0, og løpet er kjørt for denne måneden.

---

## `binary_sensor.effektvakt_kutt_ned_anbefalt`

**Hva**: `on` når hysteresefull risiko er lik eller høyere enn konfigurert `min_risiko_for_kutt` (standard `like_under_terskel`).

**Verdier**: `on` (vises som «Kutt anbefalt»), `off` («Ingen handling»), `unknown` (coordinator stale)

**Typisk bruk**: Trigger i enkel_lastkutt.yaml og climate_min_temp.yaml. Er en enklere grensesnitt enn å lese `risiko_niva` direkte.

**Egne attributter**: `automatikk_aktiv` speiler `switch.effektvakt_automatikk`, så et dashboard kan skille «burde kuttes» fra «blir kuttet» uten å slå opp entitets-id-en til switchen.

Sensoren følger ikke switchen. Den sier at risikoen er der, ikke at noen gjør noe med den. Fulgte den switchen, ville historikken vist færre kutt-verdige timer enn det faktisk var.

---

## `switch.effektvakt_automatikk`

**Hva**: Hovedbryteren for all lastkutting. Er den av, kutter ingen av blueprintene, uansett hvor mange automasjoner du har.

**Verdier**: `on` (standard), `off`

**Overlever omstart**: ja. Alt annet enn et lagret `off`, altså første oppstart, tapt historikk og `unavailable`, gir `on`.

**Hva den ikke gjør**: den rører ikke beregningen. Projisert time-snitt, risiko og kostnad regnes og vises som før, så du ser fortsatt hva timen koster mens du lar berederen gå. Den avbryter heller ikke et kutt som pågår; lasten kommer tilbake når blueprintets `max_off_minutes` løper ut. Se [blueprints.md](blueprints.md) for hvordan automasjonene leser den.

---

## Felles attributter

Alle sensorer eksponerer disse attributtene. Bruk dem i dashboards, template-sensorer eller automations.

| Attributt                     | Enhet    | Beskrivelse                                                       |
| ----------------------------- | -------- | ----------------------------------------------------------------- |
| `elapsed_minutes_in_hour`     | min      | Antall hele minutter passert i inneværende klokketime             |
| `actual_kwh_this_hour`        | kWh      | Energi målt hittil denne timen (fra energy-sensor eller estimert) |
| `current_kw`                  | kW       | Øyeblikkelig effekt fra power-sensor                              |
| `next_tier_threshold_kw`      | kW       | Konfigurert terskel for neste kapasitetstrinn                     |
| `next_tier_pris_per_maned`    | kr       | Månedspris for neste trinn                                        |
| `prev_tier_threshold_kw`      | kW       | Terskel for trinnet under (None hvis laveste trinn)               |
| `effective_threshold_kw`      | kW       | Justert terskel etter topp-3-bevissthet                           |
| `kutt_anbefalt_kw`            | kW       | `max(0, -margin)`: hvor mye som bør kuttes nå                     |
| `topp_2_snitt_denne_maned_kw` | kW       | Snitt av topp-2 dager (brukes i effective_threshold)              |
| `last_update`                 | ISO 8601 | Tidspunkt for siste vellykkede coordinator-oppdatering            |

Strategi- og kilde-attributtene ligger bare på `sensor.effektvakt_tilgjengelig_kutt`, og kostnadsattributtene bare på `sensor.effektvakt_kostnad_neste_trinn`.

### Eksempel

```yaml
# template-sensor for å lese kutt_anbefalt_kw
sensor:
  - platform: template
    sensors:
      anbefalt_kutt:
        value_template: >
          {{ state_attr('sensor.effektvakt_projisert_time_snitt', 'kutt_anbefalt_kw') }}
        unit_of_measurement: kW
```
