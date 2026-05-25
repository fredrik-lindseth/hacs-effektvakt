# Input-sensorer

Hva Effektvakt trenger fra Home Assistant for å fungere.

## TL;DR

| Sensor | Krav | Beste kilde |
|---|---|---|
| Power-sensor (W/kW) | Påkrevd | AMS-leser via HAN-port |
| Energy-sensor (kWh) | Anbefalt | Samme AMS-leser, kumulativ teller |
| VVB-power-sensor (W/kW) | Valgfri | Smart plugg med energimåling |
| Ekstra power-sensorer (W/kW) | Valgfri | Varmekabler, billader med effektmåling |

---

## Power-sensor (påkrevd)

**Hva**: Sensor som rapporterer øyeblikkelig effekt i watt eller kilowatt. Verdien skal variere i takt med at apparater slår seg på og av.

**Enheter**: `W` eller `kW`. Begge aksepteres. Sensorer i W konverteres internt til kW.

**Oppdateringsfrekvens**: Helst hvert 2-10 sekund. Sensorer som oppdateres hvert minutt mister kortvarige effektspisser og gir dårligere projeksjon.

**Maksgrense**: Effektvakt avviser verdier over 100 000 W (100 kW). Høyere verdier logges som advarsel og behandles som `unknown`.

**Kjente kilder**:
- Tibber Pulse (HAN-port, oppdaterer hvert 2-10 sek)
- Pow-U fra AMSleser.no (HAN-port, oppdaterer hvert 2 sek)
- ESPHome med P1-leser
- Aidon / Kaifa / Kamstrup via HAN-port og MQTT

Sensor-entiteten heter gjerne noe som `sensor.<ams_navn>_power` eller `sensor.<ams_navn>_p` og har enhet `W`.

### Unngå peak-sensorer

Effektvakt advarer ved oppsett hvis du velger en sensor med navn som inneholder `_max_power`, `_peak_`, `_average_` eller lignende. Peak-sensorer rapporterer maksimum- eller gjennomsnittsverdier over et intervall, ikke øyeblikkelig effekt. Projeksjon basert på slike sensorer blir feil.

Instantan effekt er bedre fordi Effektvakt selv gjør midling via energy-sensoren. Du vil ikke ha forhåndsmidlede tall inn.

---

## Energy-sensor (anbefalt)

**Hva**: Kumulativ teller som viser totalt antall kWh siden måleren ble satt opp. Verdien stiger monotont og tilsvarer det nettselskapet leser av ved fakturering.

**Enheter**: `kWh` eller `Wh`. Begge aksepteres.

**State class**: Må være `total_increasing`. Det er standardverdi for alle AMS-lesere.

**Kjente sensor-navn**:
- `sensor.<ams_navn>_active_energy_import` (vanlig OBIS 1.8.0)
- `sensor.<ams_navn>_total_consumption`
- `sensor.<ams_navn>_tpi` (Pow-U)
- `sensor.<ams_navn>_last_meter_consumption` (Tibber)

Verdien er typisk over 1 000 kWh og stiger sakte (noen kWh per time).

### Hvorfor energy-sensor gir bedre projeksjon

Uten energy-sensor estimerer Effektvakt forbruket via effekt * tid mellom ticks (tilsvarende Riemann-summering). Dette fungerer, men gir avvik hvis:

- Power-sensoren ikke oppdaterer jevnt
- HA har omstart midt i en time
- Det er nettverksforsinkelse mellom AMS-leser og HA

Med energy-sensor leses delta direkte fra den kumulative telleren. Eventuelle feil i tick-intervallet kompenseres automatisk neste tick.

---

## VVB-power-sensor (valgfri)

**Hva**: Sensor som rapporterer varmtvannstankens effektforbruk i watt eller kilowatt.

**Krav**: Krevd for strategi `vvb_status` og `vvb_pluss_ekstra`. Med `blind`-strategi brukes den ikke.

**Terskel**: Effektvakt anser VVB som aktiv hvis sensoren rapporterer over 1 000 W. Under denne grensen antas elementet å ikke varme. Norsk standard VVB (f.eks. OSO Saga 200L) har 2 000 W element.

**Kjente kilder**:
- Smart plugg med energimåling (Shelly Plug S, Sonoff S31, Zaptec Pro med OCPP)
- Clamp-on energimåler for VVB-krets

---

## Ekstra power-sensorer (valgfri)

**Hva**: En liste med sensorer for andre kuttbare laster: gulvvarme, panelovner, billader.

**Krav**: Krevd for strategi `vvb_pluss_ekstra`. Inntil 10 sensorer kan legges til.

**Terskel**: Bidrag under 100 W ignoreres (standby-forbruk telles ikke som kuttbar kapasitet).

**Eksempel-laster og typisk effekt**:

| Last | Typisk effekt |
|---|---|
| Gulvvarme, bad (5 m²) | 400-600 W |
| Panelovn | 600-1500 W |
| Billader (hjemmelader) | 3 600-22 000 W |
| Elbil (Type 2, 16 A) | 3 600 W |

En billader er den klart største enkeltkilden for kutt-kapasitet. 30 minutter pause tilsvarer 1,8-11 kWh, avhengig av ladeeffekt.

---

## Validering ved oppsett

Config flow validerer sensorer ved lagring:

1. Sensoren eksisterer i HA
2. Enheten er i godkjent liste (`W`, `kW` for power / `Wh`, `kWh` for energy)
3. Verdien er numerisk og finit
4. For power-sensor: advarsel hvis navn eller friendly name inneholder peak/max/average-mønstre

Ugyldig sensor blokkerer lagring med feilmelding.
