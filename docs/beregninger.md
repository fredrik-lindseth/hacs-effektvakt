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

### `actual_kwh_this_hour` med energy-sensor

Hvis energy-sensoren er tilgjengelig, leses delta fra hour-start:

```
actual_kwh_this_hour += max(0, energy_now - energy_at_hour_start - current_hour_kwh)
```

Kun positive delta aksepteres (kumulativ sensor kan ikke gå ned). Verdien nullstilles ved time-skifte.

Uten energy-sensor estimeres forbruket via effekt \* tid mellom ticks. Dette gir typisk 1-5 % avvik over en time, avhengig av tick-frekvens og forbruksmønster.

---

## NVE-modellen for kapasitetstrinn

Norske nettselskap bruker snittet av de tre høyeste time-forbrukene fra tre ulike dager. Effektvakt implementerer dette slik:

1. For hver fullført klokketime, ta `actual_kwh_this_hour` som timer-forbruk.
2. Sammenlign mot beste registrerte time samme dag. Oppdater hvis høyere.
3. `daily_max_kw` inneholder én verdi per dag: høyeste registrerte time den dagen.
4. `topp_3_snitt` = snitt av de 3 høyeste verdiene i `daily_max_kw`.

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

| Betingelse                      | Risiko   |
| ------------------------------- | -------- |
| `margin > 2 × buffer`           | `none`   |
| `buffer < margin <= 2 × buffer` | `low`    |
| `0 < margin <= buffer`          | `medium` |
| `margin <= 0`                   | `high`   |

Margin = `effective_threshold_kw - projected_avg`.

---

## Hysterese

Rå risiko går direkte inn i `apply_hysteresis`. Regler:

- **Oppgang** (høyere risiko): umiddelbar. Ingen ventetid.
- **Nedgang** (lavere risiko): ett trinn av gangen. Hvert trinn ned krever at det lavere nivået holder seg i `risiko_holdetid_minutter` (standard 5 min).
- Multi-step: fra `high` til `none` skjer via `high -> medium -> low -> none`, med ny tidtaker per trinn.

Eksempel: Risiko er `high`. Rå risiko faller til `none`. Etter 5 min uten ny `high` settes risiko til `medium`. Etter ytterligere 5 min til `low`. Etter 5 min til til `none`.

Dette forhindrer at VVB eller panelovn slås raskt av og på ved forbruk som svinger rundt en grense.

---

## Adaptiv tick-frekvens

Coordinator-intervallet justeres basert på risiko-nivå:

| Risiko   | Intervall   |
| -------- | ----------- |
| `none`   | 60 sekunder |
| `low`    | 60 sekunder |
| `medium` | 30 sekunder |
| `high`   | 15 sekunder |

Ved høy risiko leses sensorer og projeksjon oppdateres hvert 15 sekund for rask respons.

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
