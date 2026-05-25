# Effektvakt: kongstanke

Prediktiv effekt-styring for norske strømkunder med kapasitetsbasert nettleie.

## Hva den løser

Norske nettselskap har kapasitetsledd-trinn (typisk 2/5/10/15/20/25/50/75/100 kW). Du betaler etter snittet av topp 3 timer per måned. Treffer du neste trinn én eneste gang, betaler du for det resten av måneden.

Drømmen: når Effektvakt ser at vi er på vei til å overskride neste effekttrinn for denne timen, slår den midlertidig av valgte forbrukere (varmtvannsbereder, panelovner, billader) til risikoen er over. Brukeren havner ikke opp en effektklasse.

## Konkrekt eksempel

- Du er på kapasitetstrinn 5–10 kW (415 kr/mnd hos BKK)
- Neste trinn er 10–15 kW (600 kr/mnd)
- Margin: 2 kW under neste trinn
- Kl. 18:32: instantan effekt 9,1 kW, akkumulert kWh denne timen tilsier at maks-time-snitt blir 10,3 kW
- Effektvakt slår av VVB i 15 min
- Kl. 18:47: prosjekterte time-kWh nå 9,4 kW, trygt under taket
- VVB tilbake på

## Hvorfor egen integrasjon (ikke automasjon i Strømkalkulator)

Strømkalkulator er en **data-integrasjon**. Den regner ut hva strømmen koster. Bevisst utenfor scope: styringslogikk, switch-kommandoer, automasjoner.

Effektvakt er en **styringsintegrasjon**. Den leser data (fra Strømkalkulator-sensorer eller andre kilder) og tar handling mot fysiske switches og climate-entiteter.

Clean separation. Bytter du ut Effektvakt, fortsetter Strømkalkulator. Bytter du ut Strømkalkulator (eller bruker en annen kalkulator), kan Effektvakt fortsatt jobbe mot råe power-sensorer.

## Komplementært med eksisterende økosystem

Fra research i [docs/research/funn-fra-ha-community.md](../hacs-strømkalkulator/docs/research/funn-fra-ha-community.md) i Strømkalkulator-repoet:

- **Cheapest-hours-blueprintet** (community.home-assistant.io): triggerer last basert på spotpris. Det er pris-optimering, ikke effekt-beskyttelse. Effektvakt er ortogonal, den kan kjøre samtidig.
- **EnergyTariff (epaulsen)**: tracker kapasitetstrinn men styrer ikke noe. Vi kan lese kapasitetstrinn fra Strømkalkulator (eller EnergyTariff hvis brukeren foretrekker det) og styre.
- **Tråd 9253 (hjemmeautomasjon.no)**: PID-regulator for samme problem. Avansert, krever Python-kunnskap. Vi vil ha en config-flow-basert versjon som "bare virker".
- **EMHASS**: linear programming for batteri/PV/last. Stort scope-skille, vi gjør én ting.

## Tekniske grunnsteiner

- **Coordinator** oppdaterer hvert minutt (eventuelt hvert 30 sek hvis risiko)
- **Inputs**:
  - Power-sensor (instantan W)
  - Energi-sensor (kumulativ kWh), for å vite hvor mye som faktisk er forbrukt denne timen
  - Kapasitetstrinn-grenser (statisk konfig eller lest fra Strømkalkulator)
  - Liste over "controllable loads" (switch._ eller climate._)
- **Beregning**:
  - elapsed = time elapsed denne timen
  - actual_kwh = kWh akkumulert denne timen
  - remaining_time = 60 min − elapsed
  - projected_kwh = actual_kwh + current_power_kw × remaining_time
  - margin_kw = next_tier_threshold − projected_kwh
  - Hvis margin_kw < safety_buffer: ta handling
- **Sikkerhet**:
  - Maks av-tid per load (default 15 min)
  - Min restore-pause før vi kan slå av igjen
  - Climate-entiteter: ikke under min-temperatur (krever ekstra input fra brukeren)
  - Prioritert rekkefølge (brukeren bestemmer)
  - Failsafe: hvis coordinator dør, slår HA tilbake on automatisk (via automation eller manuell override)

## Replay-testing (krevende, men viktig)

Strømkalkulator har time-for-time-fixturer fra 6 BKK-måneder (oktober 2025–april 2026). Hver fixtur har:

- power_w per time
- kwh per time (delta fra TPI/OBIS 1.8.0)
- spot_nok_kwh_eks_mva per time

Effektvakt kan kjøre samme replay og verifisere:

1. **Predikere kapasitetstrinn-treffer**: med fixturen for desember 2025 (faktisk topp-3 = X), ville Effektvakt detektert risiko og senket toppen?
2. **Skadebegrensning**: hvor mye lavere ville topp-3-snittet vært hvis Effektvakt hadde fått slå av 1 kW i topp-timene?
3. **Falsk-positiv-rate**: hvor ofte ville Effektvakt slått av loads i situasjoner hvor det IKKE var nødvendig?

Det gir oss empirisk grunnlag for default-verdier (safety_buffer, restore-pause, etc) i stedet for gjetting.

Replay-pipeline:

- Last fixtur (samme format som Strømkalkulator-fixturer)
- For hver time: simulér minutt-for-minutt-poll med interpolert power
- La Effektvakt's terskel-logikk bestemme av/på
- Anta at en av VVB representerer ~1,5 kW reduksjon
- Beregne post-styring topp-3 og sammenligne mot faktisk topp-3

## Bevisst scope-disiplin (det vi IKKE bygger)

- VVB-styring basert på spotpris alene (det er cheapest-hours-blueprintet sitt domene)
- Batteri-arbitrage (EMHASS sitt domene)
- Solcelle-prediksjon
- Generell HA-automasjon-DSL erstatning
- Last-styring uten kapasitetstrinn-kontekst

Effektvakt gjør én ting: hindrer at du krysser kapasitetstrinn-grenser. Punktum.

## Status

- Repo: `~/dev/hacs-effektvakt/`
- Skjelett: manifest.json + hacs.json + tom const.py
- Resten: ikke startet

## Plan for ny sesjon

1. Bygge ut skjelettet basert på Strømkalkulator-mønstre:
   - `__init__.py`, `config_flow.py`, `coordinator.py`, `sensor.py`
   - `strings.json` + `translations/{nb,en}.json`
   - `tests/` med skjelett + replay-fixture-importer
   - `pyproject.toml`, `ruff.toml`, `.pre-commit-config.yaml`
   - `.github/workflows/ci.yml` + `release.yml`
   - `README.md`, `CHANGELOG.md`, `LICENSE` (MIT)
2. Implementere coordinator med terskel-logikk
3. Replay-test mot Strømkalkulator-fixturer (kopier eller refer)
4. Tune defaults basert på replay-resultater
5. Config-flow med entitetsvelger
6. Dokumentasjon: hvordan koble inn Strømkalkulator-sensorer som input

## Referanser

- Strømkalkulator-repo: `~/dev/hacs-strømkalkulator/`
- Forum-research om eksisterende løsninger: `docs/research/funn-fra-hjemmeautomasjon.md` og `docs/research/funn-fra-ha-community.md` i Strømkalkulator-repoet
- HA community-tråd 9253 (PID-tilnærming): https://www.hjemmeautomasjon.no/forums/topic/9253-prediktiv-reduksjon-av-strømbruk-effektariff-nivå/
- Strømkalkulator-faktura-fixturer (replay-grunnlag): `docs/fakturaer/` i Strømkalkulator-repoet
