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

**Hva**: Antall kW mellom projisert time-snitt og `time_tak_kw`, altså det høyeste timen kan bli uten å flytte måneden. Positiv verdi er slark, negativ verdi betyr at timen er i ferd med å flytte noe.

**Enhet**: kW

**Oppdateres**: Samme frekvens som projisert time-snitt.

**Hva den måles mot** står i attributtene, for referansen flytter seg gjennom måneden. `maal_terskel_kw` er terskelen til det billigste trinnet måneden fortsatt kan ende på, `dagstak_kw` er hva dagen i dag tåler gitt de to høyeste andre dagene, og `time_tak_kw` er det samme med dagens eget dagsmaks lagt inn. Hele regnestykket står i [beregninger.md](beregninger.md#terskelmodellen).

Navnet stemmer fortsatt: marginen er avstanden til det trinnet måneden faktisk kan ende på, og krysser du den, er det neste trinn du havner på. Fram til september 2026 var det ikke sant. Da målte sensoren mot `max(neste terskel, snitt av topp-2 dager)`, et tall uten betydning, og en lav projeksjon kunne gjøre «neste trinn» til et trinn brukeren for lengst hadde passert.

**Pålitelighet**: Avhenger av projisert time-snitt, og er mer usikker tidlig i timen. Er verdien `unknown`, finnes det ikke noe dyrere trinn å måle mot: enten er nettselskapet ukjent, eller så ligger måneden alt på øverste trinn.

---

## `sensor.effektvakt_topp_3_snitt_denne_maned`

**Hva**: Summen av de inntil tre høyeste time-forbrukene (kWh per time, ikke kW per øyeblikk) fra ulike dager hittil denne måneden, delt på tre. Dette er grunnlaget for kapasitetstrinn-fakturering (NVE-modellen).

**Enhet**: kW

**Oppdateres**: Hver gang en time fullføres, altså ved time-skifte.

**Alltid delt på tre**, også med færre enn tre dager logget. Dager som ikke finnes ennå teller som null. Det gjør tallet monotont: det stiger gjennom måneden og faller aldri fordi en rolig dag kom til. Delte sensoren på antall dager, ville to dager på 6,0 og 4,0 vist 5,0, og falt til 3,67 i det en tredje dag på 1,0 kom inn, som om noe var reddet.

Tallet er samtidig en nedre skranke for hva måneden kan ende på, og det er samme verdi som attributtet `minste_mulige_topp_3_kw` på kostnadssensoren. Det er med vilje: det skal ikke finnes to konkurrerende topp-3 i huset.

**Merk**: Sensoren viser 0,0 kW helt i starten av en ny måned (ingen dager logget ennå). Det er korrekt oppførsel, og tilbakestillingen skjer automatisk ved månedsskifte.

---

## `sensor.effektvakt_risiko_niva`

**Hva**: Hvor nær neste kapasitetstrinn timen ligger an til å komme, med hysterese. Grunnlaget er margin til neste trinn, konfigurert sikkerhetsbuffer og om timen faktisk flytter trinnet.

**Enhet**: enum

**Verdier**:

| Nivå                  | Vises som             | Betingelse                                        |
| --------------------- | --------------------- | ------------------------------------------------- |
| `god_margin`          | God margin            | Margin > 2 × sikkerhetsbuffer                     |
| `naermer_seg_terskel` | Nærmer seg terskelen  | Sikkerhetsbuffer < margin <= 2 × sikkerhetsbuffer |
| `like_under_terskel`  | Like under terskelen  | 0 < margin <= sikkerhetsbuffer                    |
| `over_terskel`        | Over terskelen        | Margin <= 0 (terskelen er overskredet)            |

De to øverste nivåene krever i tillegg at timen faktisk koster penger. Koster den ingenting, står sensoren på `naermer_seg_terskel` selv om projeksjonen ligger over taket. Det er med vilje: projeksjonen tidlig i timen er nesten bare øyeblikkseffekten, og en vannkoker skal ikke slå av berederen på en time som ender langt under. Se [kuttkriteriet i beregninger.md](beregninger.md#kuttkriteriet-flytter-denne-timen-trinnet) for utledningen og for hva ventingen koster.

Følgen er at `like_under_terskel` bare opptrer på vei ned: hysteresen går innom den når risikoen faller fra `over_terskel`. Den kan ikke lenger oppstå direkte av margin og buffer.

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

**Hva**: Kronene den inneværende timen er i ferd med å låse inn. Null nesten alltid, og spiker i det timen faktisk flytter måneden opp et trinn. Ligger måneden an til BKKs 10 kW-trinn til 415 kr, men dagene alene gir 5 kW-trinnet til 250 kr, viser sensoren 165.

Tilstanden var fram til september 2026 hoppet til neste trinn, som står stille hele måneden. En sensor som viser 185 i 30 døgn er en attributtpose og ikke en måling; hoppet ligger nå i attributtet `kostnad_neste_trinn_kr`. Timens kostnad er derimot noe en graf og en automasjon kan gjøre noe med, og blueprintene bruker den alt (`kun_varsel.yaml`).

**Enhet**: kr/mnd. Timens kostnad er også kr/mnd: det er månedsregningen timen flytter, ikke en timepris. Ingen device_class: `MONETARY` krever ISO-valutakode som enhet og en total-state_class, og satser hører hjemme i kr/mnd. Samme regel som i strømkalkulator. State class er `measurement`, så tallet kan grafes over tid.

**Trinnet du ligger an til** er trinnet til `topp_3_projisert_kw`, ikke til topp-3-snittet slik det står nå. Det er topp-3-snittet der dagens dagsmaks er byttet ut med det høyeste av dagens maks så langt og projisert time-snitt nå. Prisen er flat månedspris uten pro rata, så sensoren er like skarp den 1. som den 28.

**Oppdateres**: Samme frekvens som projisert time-snitt.

**Pålitelighet**: Både `topp_3_projisert_kw` og `minste_mulige_topp_3_kw` deler alltid på tre, så de er sammenlignbare og kan bare stige gjennom måneden. Tidlig i måneden er trinnet tilsvarende lavt: med én dag logget er to av tre plasser tomme, og måneden ligger dermed an til et billigere trinn enn den vil ende på. Se [begrensninger.md](begrensninger.md).

**Ukjent nettselskap**: Uten kapasitetstrinn er tilstanden `unknown` og alle kostnadsattributtene `None`.

### Attributter

I tillegg til fellesattributtene lenger nede:

| Attributt                   | Enhet  | Beskrivelse                                                                             |
| --------------------------- | ------ | --------------------------------------------------------------------------------------- |
| `kostnad_neste_trinn_kr`    | kr/mnd | Hoppet fra trinnet måneden ligger an til, opp til neste. 0 på øverste trinn             |
| `trinn_na_kr`               | kr/mnd | Månedsprisen for trinnet måneden ligger an til                                          |
| `trinn_na_ovre_grense_kw`   | kW     | Øvre terskel for det trinnet. `null` på øverste trinn, som ikke har noen øvre grense    |
| `trinn_neste_kr`            | kr/mnd | Månedsprisen for trinnet over. `null` når du alt er på øverste trinn                    |
| `besparelse_trinn_under_kr` | kr/mnd | Hva du sparer på å komme ned et trinn. 0 på laveste trinn                               |
| `trinn_under_oppnaelig`     | bool   | Om trinnet under fortsatt er innen rekkevidde denne måneden                             |
| `kostnad_denne_timen_kr`    | kr/mnd | Samme tall som tilstanden, beholdt som attributt for automasjoner som leser det         |
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

Siden de to øverste risikonivåene krever at timen faktisk koster penger, gjør den også det. Setter du `min_risiko_for_kutt` til `naermer_seg_terskel`, slår sensoren på også for timer som er gratis; det er den aggressive innstillingen, og den er ment slik.

**Verdier**: `on` (vises som «Kutt anbefalt»), `off` («Ingen handling»), `unknown` (coordinator stale)

**Typisk bruk**: Trigger i enkel_lastkutt.yaml og climate_min_temp.yaml. Er en enklere grensesnitt enn å lese `risiko_niva` direkte.

**Egne attributter**: `automatikk_aktiv` speiler `switch.effektvakt_automatikk`, så et dashboard kan skille «burde kuttes» fra «blir kuttet» uten å slå opp entitets-id-en til switchen.

Sensoren følger ikke switchen. Den sier at risikoen er der, ikke at noen gjør noe med den. Fulgte den switchen, ville historikken vist færre kutt-verdige timer enn det faktisk var.

---

## `switch.effektvakt_automatikk`

**Hva**: Hovedbryteren for all lastkutting. Er den av, kutter ingen av blueprintene, uansett hvor mange automasjoner du har.

**Verdier**: `on` (standard), `off`

**Overlever omstart**: ja. Alt annet enn et lagret `off`, altså første oppstart, tapt historikk og `unavailable`, gir `on`.

**Hva den ikke gjør**: den rører ikke beregningen. Projisert time-snitt, risiko og kostnad regnes og vises som før, så du ser fortsatt hva timen koster mens du lar berederen gå. Den avbryter heller ikke et kutt som pågår; lasten kommer tilbake ved neste timeskifte, og senest når blueprintets `max_off_minutes` løper ut. Se [blueprints.md](blueprints.md) for hvordan automasjonene leser den.

---

## Felles attributter

Alle sensorer eksponerer disse attributtene. Bruk dem i dashboards, template-sensorer eller automations.

| Attributt                     | Enhet    | Beskrivelse                                                       |
| ----------------------------- | -------- | ----------------------------------------------------------------- |
| `elapsed_minutes_in_hour`     | min      | Antall hele minutter passert i inneværende klokketime             |
| `actual_kwh_this_hour`        | kWh      | Energi målt hittil denne timen (fra energy-sensor eller estimert) |
| `current_kw`                  | kW       | Øyeblikkelig effekt fra power-sensor                              |
| `maal_terskel_kw`             | kW       | Terskelen til det billigste trinnet måneden fortsatt kan ende på  |
| `maal_trinn_kr`               | kr/mnd   | Månedsprisen for det trinnet                                      |
| `dagstak_kw`                  | kW       | Høyeste dagsmaks i dag som holder måneden i det trinnet           |
| `time_tak_kw`                 | kW       | `max(dagens_maks_kw, dagstak_kw)`: det marginen måles mot         |
| `dagens_maks_kw`              | kW       | Høyeste ferdige time i dag                                        |
| `topp_2_andre_dager_kw`       | kW       | Sum av de to høyeste dagsmaksene fra andre dager enn i dag        |
| `kutt_anbefalt_kw`            | kW       | `max(0, -margin)`: hvor mye som bør kuttes nå                     |
| `kan_legge_paa_kw`            | kW       | `max(0, margin)`: hvor mye time-snittet tåler å stige             |
| `last_update`                 | ISO 8601 | Tidspunkt for siste vellykkede coordinator-oppdatering            |

Radene fra `maal_terskel_kw` til `topp_2_andre_dager_kw` er terskelmodellen, i den rekkefølgen den regnes. `maal_terskel_kw`, `dagstak_kw`, `time_tak_kw` og `kan_legge_paa_kw` er `null` når det ikke finnes noe dyrere trinn å unngå, altså ved ukjent nettselskap eller på øverste trinn. Se [beregninger.md](beregninger.md#terskelmodellen).

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
