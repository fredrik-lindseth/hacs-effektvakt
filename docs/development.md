# Utvikling

## Repo-struktur

| Område | Ansvar |
| --- | --- |
| `__init__.py`, `config_flow.py` | Oppsett, migrering, tjenester og watchdog. |
| `coordinator.py`, `avlesning.py` | Hente målinger, kjøre domenelogikk og lagre tilstand. |
| `modell.py`, `timeregnskap.py`, `hysterese.py` | Terskler, timeregnskap og risiko uten HA-import. |
| `laster.py`, `lastprofil.py`, `profilestimat.py`, `lastprofiler.py` | Lastbidrag og profilanalyse. |
| `profilhistorikk.py`, `lastvern.py` | Recorder-adapter og vedvarende kuttansvar. |
| `sensor.py`, `binary_sensor.py`, `switch.py` | Entiteter og attributter. |
| `dso.py`, `oppsett.py`, `tid.py` | Tariffer, validering og faktisk tid. |
| `faceplate.py`, `frontend.py`, `www/` | SVG-skive, HA-registrering og kort. |
| `strings.json`, `translations/`, `brand/` | HA-tekster og genererte ikoner. |
| `scripts/`, `tests/`, `tests_ha/` | Lokal analyse, releaseverktøy og tester. |
| `docs/kort-harness/`, `esphome/` | Kortprøvebenk og fysisk panel. |

Integrasjonsfilene ligger i `custom_components/effektvakt/`. Arkitekturregler står i [AGENTS.md](../AGENTS.md).

## Kjøre tester

Bruk [just](https://github.com/casey/just) og [uv](https://docs.astral.sh/uv/), med låste avhengigheter fra `uv.lock`.

```bash
just test-unit             # tests/ med stubbet HA
just test-unit -k terskel   # send argumenter til pytest
just check                 # ruff, format, mypy, vulture
just test                  # kreves før commit: unit + check
just test-ha minimum       # ekte HA på lovet minimum
just test-ha current       # ekte HA på aktuell versjon
just coverage              # samlet dekning, minst 95 %
just fmt                   # skriver formatteringsendringer
```

### Miljøene

| Gruppe | Miljø | Python | HA |
| --- | --- | --- | --- |
| `unit` | `.venv-unit` | 3.13 | Stubbet |
| `kvalitet` | `.venv-kvalitet` | 3.13 | Ingen |
| `ha-minimum` | `.venv-ha-minimum` | 3.13 | 2025.1.0 |
| `ha-current` | `.venv-ha-current` | 3.14 | 2026.10.0 |

Miljøene er atskilt fordi `tests/conftest.py` stubber HA-moduler. Ekte HA i unit-miljøet ville kollidert med stubbene. Kvalitetsverktøy er pinnet til hook-versjonene.

### DSO-tabellen

```bash
just dso-hent                # pinnet kilde til _fri-nettleie/
just dso-sjekk _fri-nettleie  # uten nett
just dso-sjekk               # last ned kilden
```

## Pre-commit hooks

```bash
pre-commit install
pre-commit install --hook-type pre-push
pre-commit run --files <filene dine>
```

Hookene kjører kvalitet og filkontroller; mypy er blokkerende. Pre-push kjører `just test-unit`. DSO-hooken gjelder generator, kildetabell og generert data. Bruk eksplisitte filer ved samtidig agentarbeid.

## Oppdatere DSO-data

Ikke rediger `dso.py` for hånd. Oppdater pinnen, regenerer og les diffen; se [dso.md](dso.md#oppdatere-satsene).

## Eksportere GEHA-METER-skiven

```bash
python3 scripts/export_faceplate.py --liste
python3 scripts/export_faceplate.py --dso bkk --out bkk.svg
python3 scripts/export_faceplate.py --dso bkk --variant card --png
python3 scripts/export_faceplate.py --dso sygnir --maks-kw 30
```

Standard er `print`: flat skive uten visere. `card` gir skjermvarianten. SVG genereres uten HA; standard filnavn er `geha-meter-<dso>-<variant>.svg`. Skalaverdien rundes opp til lesbar topp. `--png` trenger `rsvg-convert` (`brew install librsvg`) og gir 1181 × 1181 piksler, skjermkorrektur ved 300 dpi/100 mm.

### Mål og tekst

viewBox `0 0 1000 1000` tilsvarer 100 × 100 mm ved riktig importskala. Konverter `<text>` til baner før trykk/gravering. Se [panelguiden](fysisk-panel.md).

## Regenerere ikonet

```bash
python3 scripts/generate_brand_images.py
python3 scripts/generate_brand_images.py --sjekk
```

Kilden er `images/icon.svg`; resultatene er 256/512-pikslers PNG-er i `brand/`. Krever `rsvg-convert`. Rediger SVG-en, aldri PNG-ene. Tester kontrollerer kildehash, størrelser, transparens, trimming og kontrast. Farger ligger i SVG-ens `<style>`; vurder også 24/48-pikslers visning på lys og mørk bakgrunn.

## Prøve Lovelace-kortet

```bash
python3 docs/kort-harness/server.py
```

Åpner `http://127.0.0.1:8799/docs/kort-harness/`, med ekte kortfil og SVG-er generert ved hver forespørsel. `--dso`, `--port` og `--ingen-nettleser` tilpasser kjøringen.

Benken viser begge stiler, 30 kW og manglende målinger. `?sen=3000` simulerer forsinket websocket-registrering. Testverdier ligger i `FELLES`, `tilstander` og `oppsett` i `index.html`; hold dem konsistente med terskelmodellen. Konsollen viser aria-tekst, farger, trinn og vinkler. Skjermlesertekst og redusert animasjon inngår i kortet. [Brukerveiledning](dashboard-kort.md).

## Deploye til lokal HA

HA er produksjon. Ta tidsstemplet backup før endring; ikke opprett testdashbord eller automasjoner der. Kopier integrasjonsfilene, start HA på nytt og kontroller logg og sensorverdier. Følg [AGENTS.md](../AGENTS.md#home-assistant-hos-fredrik).

## CI-workflows

`ci.yml` har seks jobber og en releaseport:

| Jobb | Kontroll |
| --- | --- |
| `test-unit` | Replay-fixturer, unit-tester og unit-dekning. |
| `test-ha` | Ekte HA på minimum og aktuell versjon. |
| `coverage` | Samlet dekning fra begge suitene; `just coverage-gate` krever 95 %. |
| `check` | Kvalitet, DSO-kilde, manifest og versjonssamsvar. |
| `hacs`, `hassfest` | Integrasjonsvalidering. |
| `release-gate` | Alle seks må være `success`; skipped/cancelled er feil. |

Codecov-opplasting er rådgivende; lokal coverage-port er blokkerende. `validate.yml` gjentar HACS/hassfest nattlig. [Releaseflyt](release-notes.md).

## Services

Tjenestene er tilgjengelige mens minst ett oppsett er lastet.

### `effektvakt.set_safety_buffer`

Juster sikkerhetsbuffer uten omstart:

```yaml
service: effektvakt.set_safety_buffer
data:
  kw: 1.5
```

### `effektvakt.reset_topp_3`

Nullstill lokale registrerte dagsmaks for måneden. Det endrer ikke nettselskapets fakturagrunnlag.

```yaml
service: effektvakt.reset_topp_3
```

### `effektvakt.styr_last`

Blueprintenes grensesnitt til vedvarende lastvern. Originaltilstand, eier, frist og minste påtid lagres før kutt. [Tjenestefelter](../custom_components/effektvakt/services.yaml) og [vernets kontrakt](blueprints.md#gjeninnkoblingsvern).

## Diagnostics

Last ned fra **Settings → Devices & Services → Effektvakt → Download diagnostics**. Filen inneholder oppsett, entitets-ID-er, coordinator-data, historikkgrunnlag, hysterese, tariff og lastvernets eierskap/frister. Les gjennom før deling.
