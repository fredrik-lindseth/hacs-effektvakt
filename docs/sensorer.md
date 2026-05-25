# Sensorer

Effektvakt oppretter ett device med 5 sensorer og 1 binary sensor. Alle deler et sett felles attributter.

## Oversikt

| Sensor                                       | Enhet  | State class |
| -------------------------------------------- | ------ | ----------- |
| `sensor.effektvakt_projisert_time_snitt`     | kW     | measurement |
| `sensor.effektvakt_margin_til_neste_trinn`   | kW     | measurement |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | kW     | measurement |
| `sensor.effektvakt_risiko_niva`              | enum   | -           |
| `sensor.effektvakt_tilgjengelig_kutt`        | kW     | measurement |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on/off | -           |

---

## `sensor.effektvakt_projisert_time_snitt`

**Hva**: Forventet time-snitt i kW ved slutten av inneværende klokketime, gitt at nåværende effekt holder seg til time-slutt.

**Enhet**: kW

**Oppdateres**: Hvert 60 sekund (none/low risiko), 30 sekund (medium), 15 sekund (high).

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

**Hva**: Hysteresefull risikovurdering basert på margin til neste trinn og konfigurert sikkerhetsbuffer.

**Enhet**: enum

**Verdier**:

| Nivå     | Betingelse                                        |
| -------- | ------------------------------------------------- |
| `none`   | Margin > 2 × sikkerhetsbuffer                     |
| `low`    | Sikkerhetsbuffer < margin <= 2 × sikkerhetsbuffer |
| `medium` | 0 < margin <= sikkerhetsbuffer                    |
| `high`   | Margin <= 0 (terskelen er overskredet)            |

**Hysterese**: Oppgang til høyere risiko skjer umiddelbart. Nedgang skjer ett trinn av gangen og krever at det lavere nivået holder seg i `risiko_holdetid_minutter` (standard 5 min) før det bekreftes.

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

---

## `binary_sensor.effektvakt_kutt_ned_anbefalt`

**Hva**: `on` når hysteresefull risiko er lik eller høyere enn konfigurert `min_risiko_for_kutt` (standard `medium`).

**Verdier**: `on` (kutt anbefalt), `off` (ingen handling), `unknown` (coordinator stale)

**Typisk bruk**: Trigger i enkel_lastkutt.yaml og climate_min_temp.yaml. Er en enklere grensesnitt enn å lese `risiko_niva` direkte.

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
| `ekstra_power_w_total`        | W        | Sum av ekstra-sensorer (kun for vvb_pluss_ekstra)                 |
| `kutt_strategi`               | str      | Aktiv strategi: blind / vvb_status / vvb_pluss_ekstra             |
| `last_update`                 | ISO 8601 | Tidspunkt for siste vellykkede coordinator-oppdatering            |

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
