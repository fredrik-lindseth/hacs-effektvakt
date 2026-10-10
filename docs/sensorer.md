# Sensorer

Entitetene deler én enhet og felles beregningsattributter. Tilgjengelig kutt og profilestimat opprettes bare når oppsettet gir grunnlag for dem.

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

`sensor.effektvakt_tilgjengelig_kutt` er den eneste av dem som ikke alltid finnes: den opprettes først når minst én kuttbar last er konfigurert, se [laster.md](laster.md).

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

**Pålitelighet**: Avhenger av projisert time-snitt, og er mer usikker tidlig i timen. `unknown` kan bety manglende eller utdaterte effektmålinger, ukjent eller sperret tariffmetode, eller at måneden alt ligger på øverste trinn. Se `beregning_gyldig` og `maalegrunnlag_problem` før du tolker en ukjent margin.

---

## `sensor.effektvakt_topp_3_snitt_denne_maned`

**Hva**: Summen av de inntil tre høyeste time-forbrukene (kWh per time, ikke kW per øyeblikk) fra ulike dager hittil denne måneden, delt på tre. Dette er grunnlaget for kapasitetstrinn-fakturering (NVE-modellen).

**Enhet**: kW

**Oppdateres**: Hver gang en time fullføres, altså ved time-skifte.

Snittet deles alltid på tre; manglende dager teller som null. Det viser samme nedre skranke som `minste_mulige_topp_3_kw`.

**Merk**: Sensoren viser 0,0 kW helt i starten av en ny måned (ingen dager logget ennå). Det er korrekt oppførsel, og tilbakestillingen skjer automatisk ved månedsskifte.

### Attributter

I tillegg til fellesattributtene lenger nede:

| Attributt                 | Type  | Beskrivelse                                                             |
| ------------------------- | ----- | ----------------------------------------------------------------------- |
| `topp_3_dager`            | liste | De tre dagene snittet består av, `{dato, kw}`, høyest først             |
| `topp_3_inkluderer_i_dag` | bool  | Om dagens egen dagsmaks alt er en av de tre                             |
| `dag_som_ryker`           | dict  | Dagen en høyere dagsmaks i dag ville skjøvet ut, eller `null`           |

Snittet alene sier ikke om timen du står i betyr noe. Sammensetningen gjør det: teller dagens maks alt med, bytter en ny time på samme nivå bare ut sin egen plass, og koster ingenting. Gjør den det ikke, er `dag_som_ryker` den laveste av de tre, altså den som forsvinner ut av regningen hvis dagen i dag setter en høyere topp.

`dag_som_ryker` er `null` når dagen i dag alt teller med, og når måneden har færre enn tre dager: da er det en ledig plass å fylle framfor en dag å skyve ut.

```yaml
topp_3_dager:
  - dato: "2026-06-02"
    kw: 9.5
  - dato: "2026-06-01"
    kw: 9.0
  - dato: "2026-06-03"
    kw: 2.0
topp_3_inkluderer_i_dag: false
dag_som_ryker:
  dato: "2026-06-03"
  kw: 2.0
```

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

Høy rå risiko krever oppfylt [kuttkriterium](beregninger.md#kuttkriteriet-flytter-denne-timen-trinnet). Standardvurderingen krever tariffvirkning; et valgt månedsmål kan også begrunne kutt før timen koster noe.

Følgen er at `like_under_terskel` bare opptrer på vei ned: hysteresen går innom den når risikoen faller fra `over_terskel`. Den kan ikke lenger oppstå direkte av margin og buffer.

Tilstanden er verdien i venstre kolonne. Det er den automasjoner, maler og logger sammenligner mot. Teksten i midten er oversettelsen HA viser, på norsk og engelsk.

**Hysterese**: Oppgang til et mer alvorlig nivå skjer umiddelbart. Nedgang skjer ett trinn av gangen og krever at det lavere nivået holder seg i `risiko_holdetid_minutter` (standard 5 min) før det bekreftes.

**Oppdateres**: Samme frekvens som projisert time-snitt.

---

## `sensor.effektvakt_tilgjengelig_kutt`

**Hva**: Summen av de konfigurerte kuttbare lastene som trekker over terskelen sin akkurat nå.

**Enhet**: kW

**Finnes bare med laster**: har du ikke konfigurert en eneste kuttbar last, opprettes ikke sensoren. Det er et ærligere svar enn et anslag ingen har gitt grunnlag for. Lastene legges inn under Configure, se [laster.md](laster.md).

**Merk**: Denne sensoren sier ingenting om risiko. Den er en hjelpe-sensor for blueprints og dashboards som vil vise «vi kan kutte X kW nå».

### Attributter

I tillegg til fellesattributtene lenger nede:

| Attributt       | Enhet | Beskrivelse                                             |
| --------------- | ----- | ------------------------------------------------------- |
| `kutt_kilder`   | liste | Én oppføring per konfigurert last, se under             |
| `kuttet_naa_kw` | kW    | Hvor mye last som står kuttet av Effektvakt akkurat nå  |

### `kutt_kilder`

Tilstanden er en sum, og `kutt_kilder` er postene den er summen av. Hver konfigurert last har én oppføring:

| Nøkkel         | Beskrivelse                                                                         |
| -------------- | ----------------------------------------------------------------------------------- |
| `entity_id`    | Effektsensoren lasten leses fra                                                     |
| `navn`         | Navnet du gav lasten, ellers sensorens `friendly_name`. `null` hvis ingen av delene  |
| `effekt_w`     | Effekten akkurat nå. `null` når sensoren er `unavailable`, `unknown` eller ulesbar   |
| `teller_med`   | Om lasten faktisk bidrar til tilstanden akkurat nå                                  |
| `terskel_w`    | Lastens egen terskel for «på». Standard 100 W                                       |
| `bryter`       | Bryteren som slår lasten av, eller `null` når lasten ikke har en kjent bryter        |
| `bryter_paa`   | Om bryteren står på. `null` uten bryter, og når bryteren ikke svarer                |
| `kuttet`       | Om lasten står kuttet av Effektvakt akkurat nå                                      |
| `kuttet_siden` | ISO 8601-tidspunktet kuttet begynte, eller `null`                                   |

```yaml
kutt_kilder:
  - entity_id: sensor.bereder_effekt
    navn: Varmtvannsbereder
    effekt_w: 1800.0
    teller_med: true
    terskel_w: 1000.0
    bryter: switch.bereder
    bryter_paa: true
    kuttet: false
    kuttet_siden: null
  - entity_id: sensor.varmekabler_badet_electric_consumption_w
    navn: Varmekabler badet
    effekt_w: 12.0
    teller_med: false
    terskel_w: 100.0
    bryter: null
    bryter_paa: null
    kuttet: false
    kuttet_siden: null
```

Alle konfigurerte laster er med, også de som ikke teller nå. Forskjellen mellom «finnes ikke» og «teller ikke nå» er nettopp det som er verdt å se på et dashboard. En last får `teller_med: false` når sensoren er utilgjengelig, eller når effekten ligger på eller under terskelen.

`effekt_w: null` er ikke det samme som `0`. Null watt betyr at lasten står stille, `null` betyr at vi ikke vet. Det samme skillet gjelder `bryter_paa`.

`kuttet` beskriver last som Effektvakt har overtatt gjennom lastvernet. Et manuelt avslag samtidig med et kuttvarsel er ikke alene bevis på et kutt fra Effektvakt.

Summen av `effekt_w` for oppføringene med `teller_med: true` er tilstanden til sensoren, i W mot kW.

---

## `sensor.effektvakt_kostnad_neste_trinn`

**Hva**: Kronene den inneværende timen er i ferd med å låse inn. Null nesten alltid, og spiker i det timen faktisk flytter måneden opp et trinn. Ligger måneden an til BKKs 10 kW-trinn til 415 kr, men dagene alene gir 5 kW-trinnet til 250 kr, viser sensoren 165.

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
| `trinn_under_terskel_kw`    | kW     | Terskelen til trinnet under. `null` på laveste trinn                                    |
| `trinn_under_oppnaelig`     | bool   | Om trinnet under fortsatt er innen rekkevidde denne måneden                             |
| `trinn_under_realistisk`    | bool   | Om trinnet under er noe boligen kunne siktet på i det hele tatt                          |
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

---

## `binary_sensor.effektvakt_kutt_ned_anbefalt`

**Hva**: `on` når hysteresefull risiko er lik eller høyere enn konfigurert `min_risiko_for_kutt` (standard `like_under_terskel`).

Kuttkriteriet og et eventuelt månedsmål avgjør rå risiko. Velger du `naermer_seg_terskel` som minste nivå, kan sensoren også slå på for timer uten tariffvirkning.

**Verdier**: `on` (vises som «Kutt anbefalt»), `off` («Ingen handling»), `unknown` (manglende beregningsgrunnlag eller coordinator som har stoppet)

**Typisk bruk**: Trigger i enkel_lastkutt.yaml og climate_min_temp.yaml. Er en enklere grensesnitt enn å lese `risiko_niva` direkte.

**Egne attributter**: `automatikk_aktiv` speiler `switch.effektvakt_automatikk`, så et dashboard kan skille «burde kuttes» fra «blir kuttet» uten å slå opp entitets-id-en til switchen.

Sensoren følger ikke switchen. Den sier at risikoen er der, ikke at noen gjør noe med den. Fulgte den switchen, ville historikken vist færre kutt-verdige timer enn det faktisk var.

---

## `switch.effektvakt_automatikk`

**Hva**: Hovedbryteren for all lastkutting. Er den av, kutter ingen av blueprintene, uansett hvor mange automasjoner du har.

**Verdier**: `on` (standard), `off`

**Overlever omstart**: ja. Alt annet enn et lagret `off`, altså første oppstart, tapt historikk og `unavailable`, gir `on`.

**Hva den ikke gjør**: den rører ikke beregningen. Projisert time-snitt, risiko og kostnad regnes og vises som før, så du ser fortsatt hva timen koster mens du lar berederen gå. Ved neste blueprint-vurdering, senest innen ett minutt, ber avslått automatikk om gjeninnkobling av eide laster. Lastvernets lagrede frist og gjenforsøk gjelder fortsatt. Se [blueprints.md](blueprints.md) for hvordan automasjonene leser den.

---

## Felles attributter

Alle sensorer eksponerer disse attributtene. Bruk dem i dashboards, template-sensorer eller automations.

| Attributt                     | Enhet    | Beskrivelse                                                       |
| ----------------------------- | -------- | ----------------------------------------------------------------- |
| `elapsed_minutes_in_hour`     | min      | Antall hele minutter passert i inneværende klokketime             |
| `minutter_igjen_av_timen`     | min      | Minutter igjen av klokketimen. Summerer alltid til 60 med raden over |
| `actual_kwh_this_hour`        | kWh      | Energi målt hittil denne timen (fra energy-sensor eller estimert) |
| `current_kw`                  | kW       | Øyeblikkelig effekt fra power-sensor                              |
| `maal_terskel_kw`             | kW       | Terskelen til det aktive månedsmålet, ellers det billigste oppnåelige trinnet  |
| `maal_trinn_kr`               | kr/mnd   | Månedsprisen for det trinnet                                      |
| `dagstak_kw`                  | kW       | Høyeste dagsmaks i dag som holder måneden i det trinnet           |
| `time_tak_kw`                 | kW       | `max(dagens_maks_kw, dagstak_kw)`: det marginen måles mot         |
| `dagens_maks_kw`              | kW       | Høyeste ferdige time i dag                                        |
| `topp_2_andre_dager_kw`       | kW       | Sum av de to høyeste dagsmaksene fra andre dager enn i dag        |
| `kutt_anbefalt_kw`            | kW       | Momentant kutt: `max(0, -margin) / gjenstående timer`                     |
| `kan_legge_paa_kw`            | kW       | `max(0, margin)`: hvor mye time-snittet tåler å stige             |
| `kan_legge_paa_resten_av_timen_kw` | kW  | Hvor mye last du kan slå på nå og la stå timen ut                 |
| `last_update`                 | ISO 8601 | Tidspunkt for siste coordinator-oppdatering; ikke bevis på fersk måling |
| `maalegrunnlag_gyldig`        | bool | Om effektsensoren har en gyldig, fersk verdi |
| `beregning_gyldig`            | bool | Om både målegrunnlag og støttet tariffgrunnlag finnes |
| `maalegrunnlag_problem`       | tekst | Årsak til at beregningen ikke kan gi råd, ellers `null` |

`kan_legge_paa_kw` og `kan_legge_paa_resten_av_timen_kw` svarer på to forskjellige spørsmål. Det første er hvor mye time-snittet tåler å stige, det andre hvor mye last du kan slå på. En last som står på i ti av seksti minutter flytter snittet med en sjettedel av effekten sin, så kl. 18:50 med 1 kW margin er svaret 6 kW og ikke 1. Det er «kan jeg sette på vaskemaskinen nå», og det er hele grunnen til at tallet finnes. Utledningen står i [beregninger.md](beregninger.md#resten-av-timen).

Radene fra `maal_terskel_kw` til `topp_2_andre_dager_kw` er terskelmodellen, i den rekkefølgen den regnes. `maal_terskel_kw`, `dagstak_kw`, `time_tak_kw` og `kan_legge_paa_kw` er `null` når måle-/tariffgrunnlaget mangler, eller når måneden er på øverste trinn. Bare det siste betyr at et dyrere trinn ikke finnes. Se [beregninger.md](beregninger.md#terskelmodellen).

Last-attributtene ligger bare på `sensor.effektvakt_tilgjengelig_kutt`, og kostnadsattributtene bare på `sensor.effektvakt_kostnad_neste_trinn`.

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

## Valgt månedsmål

Utviklingsversjonen legger til tre felles attributter: `valgt_maal_kw` er den konfigurerte terskelen eller `null` når målet er av, `maal_status` er `ikke_valgt`, `aktiv`, `tapt` eller `ugyldig`, og `maal_kutt_anbefalt` sier om et kutt kan begrense en ny dagsmaks over måltaket. De to siste blir `null` når måle- eller tariffgrunnlaget mangler. Målet gir ikke et sparebeløp: `timen_flytter_trinnet` og kostnadsattributtene beskriver fortsatt virkningen på kapasitetstrinnet nå. [Forutsetninger](sparepotensial.md#et-mål-for-måneden).

## Lastprofiler og estimert kuttenergi

I utviklingsversjonen opprettes `sensor.effektvakt_estimert_kuttenergi_resten_av_timen` når minst én last har en profil aktivert. Tilstanden er kWh som anslås å kunne fjernes fra den inneværende timen innenfor lastens tillatte kuttvarighet. Det er et framtidsanslag, og har ikke energiens device class eller state class for akkumulert forbruk. Sensoren må ikke brukes som målt forbruk eller målt spart energi i Energy-dashbordet.

Den eksisterende sensoren for tilgjengelig kutt beholder målt momentan effekt i kW. En manuell last uten effektsensor bidrar ikke til den målingen. Hver last med profil får et `lastprofil`-objekt i `kutt_kilder`:

| Felt | Grunnlag |
| --- | --- |
| `kilde` | Automatisk eller manuell profil |
| `datagrunnlag` | Forklaring på målt, antatt eller manglende grunnlag |
| `arbeidssyklus_pct` | Påandel i prosent |
| `aktiv_effekt_w` | Målt eller antatt effekt når aktiv |
| `dekning_pct` | Andel kjent tid i målevinduet, ikke bevis på fersk sensor |
| `hele_sykluser` | Antall hele observerte påperioder |
| `oppdatert` | Tidspunkt for profiloppdateringen |
| `periode_start`, `periode_slutt` | Målevinduet for automatisk profil |
| `estimert_kuttenergi_kwh` | Lastens estimerte bidrag til resten av timen |
| `forventet_drift_minutter` | Forventet drift innenfor vurdert tidsvindu |
| `stoette_antall` | Historiske sykluser som støtter restvarighetsanslaget |
| `maks_kutt_minutter` | Lastens konfigurerte grense for estimatet |

Profilgrunnlaget vises også på estimatsensoren. [Metodikken](lastprofiler.md) beskriver tidsvekting, hele sykluser og manuelle antakelser. Når det valgfrie profilvalget i innstillingene er på, brukes energianslag fra målte aktive laster i kuttvurderingen. Manuelle profiler uten effektmåling gir bare planleggingsanslag. Profilene erstatter ikke blueprintenes lastvalg eller lastvernets tidsgrenser.
