# Beregninger

Implementasjon: [`coordinator.py`](../custom_components/effektvakt/coordinator.py) og [`const.py`](../custom_components/effektvakt/const.py).

## Projisert time-snitt

Hvert tick beregnes forventet time-snitt i kW ved time-slutt:

```
projected_avg = actual_kwh_this_hour + current_kw * remaining_h
```

Hvor:

- `actual_kwh_this_hour`: energi målt hittil denne timen (kWh)
- `current_kw`: øyeblikkelig effekt fra power-sensor (kW)
- `remaining_h`: andel av timen som gjenstår (`1.0 - elapsed_h`)
- `elapsed_h`: `(now.minute + now.second / 60) / 60`

Eksempel kl. 18:45, 2,4 kWh brukt, 3,2 kW nå:

```
elapsed_h      = (45 + 0/60) / 60 = 0.75
remaining_h    = 1.0 - 0.75 = 0.25
projected_avg  = 2.4 + 3.2 * 0.25 = 3.2 kW
```

### `actual_kwh_this_hour`

Timen bygges av to kilder som avstemmes mot hverandre, ikke av energy-sensoren alene.

**Effektintegrasjon hvert tick.** Energien mellom to tick er trapesregelen over de to
effektavlesningene, med faktisk tid mellom tidsstemplene:

```
kwh = (forrige_kw + na_kw) / 2 * timer_mellom_ticks
```

Tiden hentes fra tidsstemplene og ikke fra et antatt tickintervall, for ticket hopper over
når HA har det travelt. Trapesregelen framfor å holde den forrige avlesningen: en last som
slås av og på treffer like ofte før som etter en avlesning, og da er midtverdien uten
systematisk slagside. Går det mer enn fem minutter mellom to tick, har HA vært nede eller
stått fast, og da integreres intervallet ikke i det hele tatt (se `MAX_INTEGRATION_GAP_H`).

Siste effektavlesning lagres, så en omstart som tar under fem minutter integreres over
med den effekten som sto da HA gikk ned. Det er et anslag, men et bundet et, og
energy-sensoren retter det ved neste avlesning.

**Energy-sensoren korrigerer.** Måleren er den nøyaktige kilden og skal vinne, men den
legges ikke oppå anslaget. Coordinatoren holder rede på hvor mye av timen som er integrert
anslag og ikke bekreftet av måleren (`_estimert_siden_maaler_kwh`), og når måleren flytter
seg byttes nettopp den delen ut:

```
actual_kwh_this_hour = actual_kwh_this_hour - estimert_siden_maaler + maalerens_andel
```

Dermed telles ingenting to ganger, og en måler som oppdaterer hvert tiende sekund gir
nøyaktig sin egen differanse. Står måleren stille, er det ingenting å avstemme, og
anslaget får stå. Vi kan ikke se forskjell på en måler med null forbruk og en som bare
ikke har rapportert ennå.

Går måleren ned, er den nullstilt eller byttet. Hopper den mer enn `MAX_ENERGY_DELTA_KWH`,
er avlesningen ikke til å stole på uansett. I begge tilfeller beholdes det som alt er målt
denne timen, og tellingen fortsetter fra den nye standen.

Uten energy-sensor er integrasjonen alt som finnes, og timen blir like god som
effekt-sensoren og tick-frekvensen tillater. Typisk 1-5 % avvik over en time.

### kWh som kommer etter timeskiftet

En norsk HAN-avleser rapporterer gjerne 13 sekunder på timen, altså etter at timen den
måler er over. Den kWh-en hører til timen før. Tre ting gjør at den havner riktig:

1. **Tidspunktet er målerens, ikke ticket sitt.** `last_changed` på energy-sensoren sier
   når måleren faktisk meldte seg. Ticket som leser den kommer gjerne et halvt minutt
   senere, og brukes det tidspunktet i stedet, havner hele timen på feil side av skiftet.
2. **Timeskiftet deler integrasjonen.** Ligger et timeskifte mellom to tick, interpoleres
   effekten ved skiftet og energien deles i to. Den delen som lå før, følger med over til
   timen som ble ferdig.
3. **Timen holdes åpen for retting.** `_finalize_hour` låser timen inn med det vi vet ved
   timeskiftet, men beholder den som en `VentendeTime` med `dagsmaks_foer`, altså
   dagsverdien slik den sto før. Kommer avlesningen som dekker skiftet, byttes den
   estimerte delen ut og timen låses inn på nytt, også nedover. Så snart måleren har
   bekreftet tiden forbi skiftet, er timen gjort opp og kan ikke ta imot mer.

Fordelingen av en måleravlesning mellom de to timene følger anslaget, ikke tiden: måleren
sier hvor mye som gikk med, integrasjonen sier når. Vekten er ikke anslaget rått, men
snitteffekten vi faktisk målte ganget med den tiden av måler-vinduet som ligger i timen.
Forskjellen betyr noe når HA kom opp igjen fem minutter før timen var omme: fem minutter
med anslag er for lite til å veies mot tretten sekunder av den neste timen, og uten
skaleringen ville den nye timen fått en tiendedel av forrige times kWh i fanget. Er
anslaget null, altså ingen effekt-sensor, deles det på tid i stedet. Rekker vinduet mellom to avlesninger lenger
tilbake enn de to timene vi kan rette på, skaleres kWh-en ned til den andelen av tiden som
faktisk lar seg plassere. Resten hører til timer som er låst, og å legge den på timen vi
står i ville bygget en falsk topp.

### `kwh_maalt_fra_minutt`

Hvilket minutt av den inneværende timen vi har sammenhengende måling fra. Null i normal
drift. Over null betyr at `actual_kwh_this_hour` mangler starten av timen, og da er
projeksjonen for lav. Det skjer i to tilfeller:

- Integrasjonen ble satt opp midt i en time. Vi kan ikke integrere bakover, og finner ikke
  på et tall for det vi ikke så.
- HA var nede lenger enn `MAX_INTEGRATION_GAP_H`, eller effekt-sensoren var utilgjengelig.

Dekningen utvides av seg selv så snart energy-sensoren rapporterer en avlesning som rekker
tilbake til før hullet, for den kWh-en inneholder det vi gikk glipp av. Med en timesmåler
skjer det ved neste timeskifte. Uten energy-sensor står hullet ut timen. Tallet ligger i
coordinator-data og i diagnostikken, og er ikke en egen sensor.

---

## NVE-modellen for kapasitetstrinn

Norske nettselskap bruker snittet av de tre høyeste time-forbrukene fra tre ulike dager. Effektvakt implementerer dette slik:

1. For hver fullført klokketime, ta `actual_kwh_this_hour` som timer-forbruk.
2. Sammenlign mot beste registrerte time samme dag. Oppdater hvis høyere.
3. `daily_max_kw` inneholder én verdi per dag: høyeste registrerte time den dagen.
4. `topp_3_snitt` = snitt av de 3 høyeste verdiene i `daily_max_kw`.

Dagsverdien settes med max mot det dagen hadde før timen ble lagt inn, ikke mot det den
har nå. Forskjellen betyr noe når en måleravlesning retter den timen som nettopp ble låst
inn: rettingen skal også kunne gå nedover, uten at den må konkurrere med seg selv. En
omstart som kjører innlåsingen på nytt for den samme timen kan fortsatt ikke telle dobbelt.

Dette er dag-snitt av maks-timer, ikke rå time-verdier. Modellen er identisk med Elhubs metode for kapasitetstrinn-bestemmelse.

---

## `effective_threshold_kw`

For å ta hensyn til at topp-3-dagene delvis er satt, justeres terskelen:

```
Hvis < 2 dager logget:
    effective_threshold = next_tier_threshold_kw

Ellers:
    topp_2 = snitt av 2 høyeste daily_max_kw
    effective_threshold = max(next_tier_threshold_kw, topp_2)
```

Begrunnelse: Hvis du allerede har to dager med snitt på 9,5 kW, og neste trinn er på 10 kW, er den reelle terskelen 10,5 kW (slik at topp-3-snittet holdes under 10 kW). `effective_threshold` gjenspeiler dette.

---

## Kostnad for neste trinn

`compute_kostnad` i coordinator.py regner ut hva kapasitetsleddet koster og hva som står på spill akkurat nå. Resultatet mater `sensor.effektvakt_kostnad_neste_trinn`.

Først: hvilket trinn ligger måneden an til?

```
projiserte_dager       = daily_max_kw, men dagens verdi byttes ut med
                         max(daily_max_kw[i dag], projisert_time_snitt)
topp_3_projisert_kw    = snitt av de 3 høyeste i projiserte_dager
```

Trinnet er det laveste med terskel >= `topp_3_projisert_kw`. Over høyeste terskel havner du på øverste trinn. Derfra:

```
trinn_na_kr                = månedspris for det trinnet
trinn_na_ovre_grense_kw    = terskelen for det trinnet (null på øverste trinn)
trinn_neste_kr             = månedspris for trinnet over (null på øverste trinn)
kostnad_neste_trinn_kr     = trinn_neste_kr - trinn_na_kr   (0 på øverste trinn)
besparelse_trinn_under_kr  = trinn_na_kr - pris for trinnet under   (0 på laveste)
```

Prisene er flate månedspriser. Ingen pro rata, så tallet er like stort den 1. som den 28. Det er hele månedsregningen som står på spill uansett når i måneden toppen settes.

### `minste_mulige_topp_3_kw`

Nedre skranke for hva måneden kan ende på:

```
minste_mulige_topp_3_kw = sum av inntil 3 høyeste daily_max_kw / 3
```

Alltid delt på 3, uansett hvor mange dager som er logget, og bare dagsmaks som alt er låst inn telles. Den inneværende timen holdes utenfor nettopp fordi den fortsatt kan kuttes. Å telle den med ville gjort tallet pessimistisk og kunne sagt at trinnet under er uoppnåelig når det faktisk er innen rekkevidde.

```
trinn_under_oppnaelig = minste_mulige_topp_3_kw <= terskel for trinnet under
```

Én dag på 7 kW gir 2,33 og trinnet under er oppnåelig. Tre dager på 6, 7 og 8 gir 7,0, og da er løpet kjørt.

### `kostnad_denne_timen_kr`

Kronene den inneværende timen er i ferd med å låse inn:

```
kostnad_denne_timen_kr = max(0, trinn_na_kr - pris for trinnet topp_3_snitt
                                              uten denne timen gir)
```

Klemmen mot null trengs fordi `topp_3_snitt` tidlig i måneden deler på antall dager, ikke på 3 (se `top_n_average`). To dager på 12 kW gir topp-3 lik 12, mens en projeksjon som drar inn en rolig tredje dag gir 8,17. Da ligger det projiserte trinnet under det nåværende, og differansen blir negativ uten klemmen.

### Uendelig øverste terskel

Øverste kapasitetstrinn har `float("inf")` som terskel i `dso.py`. `inf` er ugyldig JSON og knekker både recorder og websocket, så både `trinn_na_ovre_grense_kw` og øverste par i `kapasitetstrinn`-attributtet sendes som `null`.

### Ukjent nettselskap

Tomt trinn-sett gir `None` på alle ti kostnadsfeltene, og sensoren står som `unknown`.

---

## Risikoklassifisering

Rå risiko bestemmes av margin og konfigurert `safety_buffer_kw` (standard 1,0 kW):

| Betingelse                      | Risiko                |
| ------------------------------- | --------------------- |
| `margin > 2 × buffer`           | `god_margin`          |
| `buffer < margin <= 2 × buffer` | `naermer_seg_terskel` |
| `0 < margin <= buffer`          | `like_under_terskel`  |
| `margin <= 0`                   | `over_terskel`        |

Margin = `effective_threshold_kw - projected_avg`.

---

## Hysterese

Rå risiko går direkte inn i `apply_hysteresis`. Regler:

- **Oppgang** (høyere risiko): umiddelbar. Ingen ventetid.
- **Nedgang** (lavere risiko): ett trinn av gangen. Hvert trinn ned krever at det lavere nivået holder seg i `risiko_holdetid_minutter` (standard 5 min).
- Multi-step: fra `over_terskel` til `god_margin` skjer via `over_terskel -> like_under_terskel -> naermer_seg_terskel -> god_margin`, med ny tidtaker per trinn.

Eksempel: Risiko er `over_terskel`. Rå risiko faller til `god_margin`. Etter 5 min uten ny `over_terskel` settes risiko til `like_under_terskel`. Etter ytterligere 5 min til `naermer_seg_terskel`. Etter 5 min til til `god_margin`.

Dette forhindrer at VVB eller panelovn slås raskt av og på ved forbruk som svinger rundt en grense.

---

## Adaptiv tick-frekvens

Coordinator-intervallet justeres basert på risiko-nivå:

| Risiko                | Intervall   |
| --------------------- | ----------- |
| `god_margin`          | 60 sekunder |
| `naermer_seg_terskel` | 60 sekunder |
| `like_under_terskel`  | 30 sekunder |
| `over_terskel`        | 15 sekunder |

Er terskelen passert, leses sensorer og projeksjon oppdateres hvert 15 sekund for rask respons.

---

## Tilgjengelig kutt per strategi

`compute_tilgjengelig_kutt_kw` i coordinator.py:

| Strategi           | Logikk                                                                  |
| ------------------ | ----------------------------------------------------------------------- |
| `blind`            | Returnerer `BLIND_ASSUMED_KUTT_KW` = 0,3 kW (2 kW VVB × 15% duty cycle) |
| `vvb_status`       | VVB-effekt / 1000 hvis VVB > 1000 W, ellers 0,0 kW                      |
| `vvb_pluss_ekstra` | VVB-bidrag + sum av ekstra-sensorer > 100 W terskel                     |

Terskelen på 1000 W for VVB er satt fordi elementet er enten fullt på (~2 kW) eller av. Verdier mellom 0 og 1000 W antas å være standby-forbruk, ikke aktiv oppvarming.

---

## DST-håndtering

Time-bucket bestemmes av `(now.hour, now.utcoffset())`. Ved overgang til/fra sommertid endres utcoffset, noe som fanger klokkeskiftet uten å forveksle det med et vanlig time-skifte. Klokken 02:00 (DST frem) og 03:00 (DST tilbake) håndteres korrekt uten å lage dobbel- eller manglende time-registrering.
