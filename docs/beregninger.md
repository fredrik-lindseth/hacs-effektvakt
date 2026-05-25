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

Uten energy-sensor estimeres forbruket via effekt * tid mellom ticks. Dette gir typisk 1-5 % avvik over en time, avhengig av tick-frekvens og forbruksmønster.

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

## Risikoklassifisering

Rå risiko bestemmes av margin og konfigurert `safety_buffer_kw` (standard 1,0 kW):

| Betingelse | Risiko |
|---|---|
| `margin > 2 × buffer` | `none` |
| `buffer < margin <= 2 × buffer` | `low` |
| `0 < margin <= buffer` | `medium` |
| `margin <= 0` | `high` |

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

| Risiko | Intervall |
|---|---|
| `none` | 60 sekunder |
| `low` | 60 sekunder |
| `medium` | 30 sekunder |
| `high` | 15 sekunder |

Ved høy risiko leses sensorer og projeksjon oppdateres hvert 15 sekund for rask respons.

---

## Tilgjengelig kutt per strategi

`compute_tilgjengelig_kutt_kw` i coordinator.py:

| Strategi | Logikk |
|---|---|
| `blind` | Returnerer `BLIND_ASSUMED_KUTT_KW` = 0,3 kW (2 kW VVB × 15% duty cycle) |
| `vvb_status` | VVB-effekt / 1000 hvis VVB > 1000 W, ellers 0,0 kW |
| `vvb_pluss_ekstra` | VVB-bidrag + sum av ekstra-sensorer > 100 W terskel |

Terskelen på 1000 W for VVB er satt fordi elementet er enten fullt på (~2 kW) eller av. Verdier mellom 0 og 1000 W antas å være standby-forbruk, ikke aktiv oppvarming.

---

## DST-håndtering

Time-bucket bestemmes av `(now.hour, now.utcoffset())`. Ved overgang til/fra sommertid endres utcoffset, noe som fanger klokkeskiftet uten å forveksle det med et vanlig time-skifte. Klokken 02:00 (DST frem) og 03:00 (DST tilbake) håndteres korrekt uten å lage dobbel- eller manglende time-registrering.
