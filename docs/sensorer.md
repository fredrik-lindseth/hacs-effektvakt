# Sensorer

Entitetene deler én enhet. Visningsnavn følger HA-språket, mens entitets-ID-ene er like på norsk og engelsk; egne omdøpinger beholdes. Alle beregninger krever ferskt målegrunnlag og støttet tariff. Se [sensorinnganger](input-sensorer.md) og [formler](beregninger.md).

## Oversikt

| Sensor                                       | Enhet  | State class |
| -------------------------------------------- | ------ | ----------- |
| `sensor.effektvakt_projisert_time_snitt`     | kW     | measurement |
| `sensor.effektvakt_margin_til_neste_trinn`   | kW     | measurement |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | kW     | measurement |
| `sensor.effektvakt_risiko_niva`              | enum   | -           |
| `sensor.effektvakt_tilgjengelig_kutt`        | kW     | measurement |
| `sensor.effektvakt_estimert_kuttenergi_resten_av_timen` | kWh | - |
| `sensor.effektvakt_kostnad_neste_trinn`      | kr/mnd | measurement |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on/off | -           |
| `switch.effektvakt_automatikk`               | on/off | -           |

Tilgjengelig kutt opprettes med minst én målt last. Estimert kuttenergi opprettes med minst én aktivert profil; den er et anslag i kWh uten device class eller state class for akkumulert energi.

## `sensor.effektvakt_projisert_time_snitt`

Forventet timegjennomsnitt hvis effekten fortsetter som nå: `actual_kwh_this_hour + current_kw × gjenstående_timer`. Tidlig i timen dominerer framskrivningen. Oppdateres hvert 60. sekund ved lav risiko, 30. sekund like under terskelen og 15. sekund over.

## `sensor.effektvakt_margin_til_neste_trinn`

`time_tak_kw − projisert_time_snitt`. Positiv verdi er margin, negativ verdi er overskridelse av timetaket. Taket tar hensyn til andre dager og dagens registrerte topp. Negativ margin betyr ikke alltid dyrere nettleie; se [terskelmodellen](beregninger.md#terskelmodellen).

Ukjent margin kan skyldes manglende måling, sperret tariff eller øverste kapasitetstrinn. Bare det siste betyr at et dyrere trinn ikke finnes; les `beregning_gyldig` og `maalegrunnlag_problem`.

## `sensor.effektvakt_topp_3_snitt_denne_maned`

Summen av de inntil tre høyeste registrerte timegjennomsnittene fra ulike dager, alltid delt på tre. Manglende dager teller som null. Fullførte timer oppdaterer grunnlaget; sene måleravlesninger kan korrigere det. Nullstilles automatisk ved månedsskiftet.

| Attributt                 | Type  | Beskrivelse                                                             |
| ------------------------- | ----- | ----------------------------------------------------------------------- |
| `topp_3_dager`            | liste | De tre dagene snittet består av, `{dato, kw}`, høyest først             |
| `topp_3_inkluderer_i_dag` | bool  | Om dagens egen dagsmaks alt er en av de tre                             |
| `dag_som_ryker`           | dict  | Dagen en høyere dagsmaks i dag ville skjøvet ut, eller `null`           |

`dag_som_ryker` er `null` når dagens topp allerede teller med eller færre enn tre dager er registrert. En ny time på samme nivå som dagens topp øker ikke dagsmaksen.

## `sensor.effektvakt_risiko_niva`

Risiko følger margin, sikkerhetsbuffer og [kuttkriterium](beregninger.md#kuttkriteriet-flytter-denne-timen-trinnet). Tabellen viser marginens nivå før kuttkriteriet og hysterese:

| Nivå                  | Vises som             | Betingelse                                        |
| --------------------- | --------------------- | ------------------------------------------------- |
| `god_margin`          | God margin            | Margin > 2 × sikkerhetsbuffer                     |
| `naermer_seg_terskel` | Nærmer seg terskelen  | Sikkerhetsbuffer < margin <= 2 × sikkerhetsbuffer |
| `like_under_terskel`  | Like under terskelen  | 0 < margin <= sikkerhetsbuffer                    |
| `over_terskel`        | Over terskelen        | Margin <= 0 (terskelen er overskredet)            |

Høy rå risiko krever kuttkriteriet eller et aktivt månedsmål. `like_under_terskel` oppstår normalt på vei ned gjennom hysterese. Oppgang er umiddelbar; nedgang krever holdetiden per trinn, standard fem minutter. Automatisering bruker kodene i venstre kolonne, ikke oversatte navn.

## `sensor.effektvakt_tilgjengelig_kutt`

Sum av målte laster strengt over sin terskel, i kW. Viser tilgjengelig effekt, ikke risiko eller energi som kan flyttes. Manuelle profiler uten effektsensor bidrar ikke.

`kuttet_naa_kw` beskriver last som står kuttet av Effektvakt. Se [lastoppsett](laster.md).

### `kutt_kilder`

Én oppføring per konfigurert last, også når den ikke bidrar nå:

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

`null` betyr ukjent, ikke null watt eller bekreftet avslag. `kuttet` krever eierskap i lastvernet; et samtidig manuelt avslag er ikke bevis på Effektvakt-kutt. Summen av `effekt_w` med `teller_med: true`, delt på 1 000, gir sensortilstanden.

## `sensor.effektvakt_kostnad_neste_trinn`

Viser `kostnad_denne_timen_kr`: forskjellen mellom kapasitetstrinnet med dagens projeksjon og trinnet registrerte dagsmaks alene gir. Eksempel: 415 − 250 = 165 kr ekstra for måneden. Enheten er `kr/mnd`, ikke en timepris; ingen pro rata eller monetary device class brukes.

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

`kapasitetstrinn` inneholder `[øvre_kW_grense, månedspris]`. Øverste grense er `null`, fordi uendelig ikke kan sendes som JSON. Tidlig i måneden er to eller tre dagsplasser fortsatt tomme. Kostnaden beskriver nåværende grunnlag, ikke en prognose for resten av måneden.

## `binary_sensor.effektvakt_kutt_ned_anbefalt`

`on` når risikoen etter hysterese når konfigurert minste nivå, standard `like_under_terskel`. `off` betyr ingen anbefaling; `unknown` betyr manglende grunnlag eller stoppet coordinator. Velger du `naermer_seg_terskel`, kan rådet komme uten tariffvirkning.

`automatikk_aktiv` speiler hovedbryteren. Anbefalingen beregnes også med bryteren av; den beviser ikke at en automasjon kutter.

## `switch.effektvakt_automatikk`

På som standard, husker lagret av-stilling. Hindrer nye kutt fra blueprints som har fått bryteren i `automatikk_switch`. Beregningene fortsetter. Eide laster slippes ved neste blueprint-vurdering, senest innen ett minutt; lastvernets frister og gjenforsøk gjelder uansett. Varsler stoppes ikke. Se [blueprintene](blueprints.md#hovedbryteren).

## Felles attributter

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

`kan_legge_paa_kw` gjelder endring av hele timegjennomsnittet; `kan_legge_paa_resten_av_timen_kw` gjelder effekt du kan slå på nå. Med ti minutter igjen og 1 kW margin er sistnevnte 6 kW. Uten terskel eller gyldig grunnlag er terskelrådene `null`.

Lastattributter finnes på tilgjengelig-kutt-sensoren, kostnadsattributter på kostnadssensoren. En attributt leses for eksempel med `{{ state_attr('sensor.effektvakt_projisert_time_snitt', 'kutt_anbefalt_kw') }}`.

## Valgt månedsmål

Utviklingsversjonen har `valgt_maal_kw` (terskel eller `null`), `maal_status` (`ikke_valgt`, `aktiv`, `tapt`, `ugyldig`) og `maal_kutt_anbefalt` (kan kuttet begrense en ny dagsmaks?). De to siste er `null` uten gyldig grunnlag. Målet gir ikke et eget sparebeløp; kostnadsattributtene beskriver tariffvirkningen nå. Se [månedsmålet](sparepotensial.md#et-mål-for-måneden).

## Lastprofiler og estimert kuttenergi

`sensor.effektvakt_estimert_kuttenergi_resten_av_timen` anslår energi som kan fjernes fra timen innenfor tillatt kuttvarighet. Den må ikke brukes som målt forbruk eller spart energi i Energy-dashbordet. Målt tilgjengelig kutt beholder kW.

Hver profilert last får `lastprofil` i `kutt_kilder`:

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

Profilgrunnlaget vises også på estimatsensoren. Med det valgfrie profilvalget på brukes anslag fra målte aktive laster i kuttvurderingen. Manuelle profiler uten måling er bare planleggingsanslag. Profiler velger ikke enkeltlaster og erstatter ikke blueprintenes tidsgrenser. Se [metodikken](lastprofiler.md).
