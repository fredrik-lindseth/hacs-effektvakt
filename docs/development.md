# Utvikling

## Repo-struktur

```
custom_components/effektvakt/
    __init__.py         # Entry-setup, watchdog, service-registrering
    binary_sensor.py    # binary_sensor.effektvakt_kutt_ned_anbefalt
    brand/              # icon.png og icon@2x.png, generert (HA leser brand-bilder herfra)
    config_flow.py      # Config flow og options flow
    const.py            # Konstanter og default-verdier
    coordinator.py      # Beregningslogikk, hysterese, persist
    diagnostics.py      # HA diagnostics-support
    dso.py              # Kapasitetstrinn per DSO (auto-generert)
    faceplate.py        # SVG-kilde for GEHA-METER-skiven (kort og trykk)
    manifest.json       # HA integration manifest
    sensor.py           # De seks sensor-entitetene
    services.yaml       # Service-definisjoner

docs/
    blueprints/         # Blueprint YAML-filer
    kort-harness/       # Prøvebenk for Lovelace-kortet, uten Home Assistant
    beregninger.md
    begrensninger.md
    blueprints.md
    development.md
    dso.md
    faq.md
    input-sensorer.md
    sensorer.md
    strategi.md

images/
    icon.svg            # Kilden til integrasjonsikonet

scripts/
    export_faceplate.py               # Eksporter skiven til SVG for trykk og CAD
    generate_brand_images.py          # Rendre icon.svg til brand/-PNG-ene
    sync_dso_from_stromkalkulator.py  # Sync DSO-data fra strømkalkulator

tests/
    conftest.py
    fixtures/
    test_*.py
```

---

## Kjøre tester

```bash
# Installer dev-avhengigheter
pip install -e ".[dev]"

# Kjør alle tester
pytest tests/ -v

# Kjør med coverage
pytest tests/ --cov=custom_components/effektvakt --cov-report=term-missing

# Kjør spesifikk testfil
pytest tests/test_coordinator_projection.py -v
```

---

## Pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files
```

Hooks kjører ruff (lint + format), mypy og vulture. CI kjører de samme sjekkene.

---

## Oppdatere DSO-data

DSO-data i `custom_components/effektvakt/dso.py` er auto-generert fra `hacs-strømkalkulator/custom_components/stromkalkulator/dso.py`. Kjør synk-scriptet:

```bash
python scripts/sync_dso_from_stromkalkulator.py
```

Scriptet forutsetter at `hacs-strømkalkulator` ligger parallelt med `hacs-effektvakt` (dvs. `../hacs-strømkalkulator`). Etter generering: kjør tester og commit `dso.py`.

DSO-test i `tests/test_dso_data.py` verifiserer at alle trinn-lister er sortert, har gyldige terskel-verdier og at prisene er positive.

---

## Eksportere GEHA-METER-skiven

`custom_components/effektvakt/faceplate.py` tegner skiven som SVG, og både dashboard-kortet og den fysiske plata kommer fra den samme kilden. `scripts/export_faceplate.py` skriver den til fil:

```bash
# Hvilke DSO-er finnes?
python3 scripts/export_faceplate.py --liste

# Skiven for BKK, klar for trykk
python3 scripts/export_faceplate.py --dso bkk --out bkk.svg

# Kortvarianten med visere og deksel, med PNG-korrektur ved siden av
python3 scripts/export_faceplate.py --dso bkk --variant card --png

# Skala opp til 30 kW for et anlegg med høyere trinn
python3 scripts/export_faceplate.py --dso sygnir --maks-kw 30
```

Scriptet laster `dso.py` og `faceplate.py` rett fra fil med importlib, så det kjører uten at Home Assistant er installert. Uten `--out` havner filen i arbeidskatalogen som `geha-meter-<dso>-<variant>.svg`. `--variant print` er standard og gir flate farger uten visere, siden viserne på den fysiske plata er av metall. `--variant card` legger på visere, slitasje og plastdeksel, altså det kortet viser. `--maks-kw` løftes opp til nærmeste skalatopp som gir hele hovedtall, så 10 gir 0 2 4 6 8 10 og 15 gir 0 3 6 9 12 15, og scriptet sier fra når verdien flyttes. Skriver du en DSO-id feil, foreslår det nærmeste treff og peker på `--liste` i stedet for å kaste en stacktrace. Id-en kan også oppgis som nettselskapets navn (`--dso BKK`).

`--png` kjører `rsvg-convert` og legger PNG-en ved siden av SVG-en, 1181 x 1181 piksler som er 300 dpi ved 100 mm. Det er korrektur for skjerm, ikke en trykkfil. Mangler `rsvg-convert`, sier scriptet fra at den installeres med `brew install librsvg`.

### Mål og tekst

SVG-en er 100 mm i faktisk størrelse. viewBox er `0 0 1000 1000` der én enhet er 0,1 mm, altså 1000 enheter = 100 mm, så filen kan tas rett inn i CAD med kjent skala.

Teksten ligger som ekte `<text>`-elementer med en fontstakk, ikke som baner. Den må konverteres til baner før den går til gravering eller trykk, ellers blir bokstavformene det maskinen tilfeldigvis har installert. Inkscape (`inkscape --export-text-to-path`) finnes ikke på denne maskinen, så konverteringen gjøres i CAD-programmet eller hos trykkeriet.

---

## Regenerere ikonet

Integrasjonsikonet er én SVG, `images/icon.svg`, og PNG-ene Home Assistant leser er
generert fra den:

```bash
python3 scripts/generate_brand_images.py          # skriv PNG-ene
python3 scripts/generate_brand_images.py --sjekk  # exit 1 hvis de er utdaterte
```

Filene havner i `custom_components/effektvakt/brand/` som `icon.png` (256x256) og
`icon@2x.png` (512x512). HA serverer brand-bilder for custom integrations derfra før den
går til brands-CDN-en, og betingelsen er at mappen heter `brand` og ligger rett i
integrasjonsmappen (`integration.has_branding` i HA sin `loader.py`). De samme PNG-ene er
materialet til PR-en mot `home-assistant/brands`.

Rendringen trenger `rsvg-convert` (`brew install librsvg`). Hver PNG bærer SHA-256-en av
SVG-en den kom fra i en tEXt-chunk, så `tests/test_brand_images.py` kjenner igjen en
utdatert PNG uten å kunne rendre selv. Den testen er fasit på ikonet: størrelser,
gjennomsiktighet, trimming, at alle fire kantene er nådd, og at fargetokenet holder 3:1
mot både hvit og HA sin mørke bakgrunn. Rediger aldri PNG-ene for hånd.

Farger skrives bare som klasseregler i `<style>`-blokken i SVG-en, aldri i tegneelementene.
Ikonet er kabinettet med skivebuen og viseren skåret ut av plata, så ingenting inne i
motivet trenger å holde kontrast på egen hånd: hullene viser siden bak.

Skal ikonet endres, døm det i liten størrelse før du tror på det. Kontaktark:

```bash
for s in 256 48 24; do
  rsvg-convert --width $s --height $s --format png images/icon.svg -o /tmp/e-$s.png
  magick /tmp/e-$s.png -background "#ffffff" -flatten /tmp/lys-$s.png
  magick /tmp/e-$s.png -background "#111111" -flatten /tmp/mork-$s.png
done
```

---

## Prøve Lovelace-kortet

`python3 docs/kort-harness/server.py` kjører kortet i nettleseren uten Home
Assistant, med skiver generert fra `faceplate.py` og kortfilen lastet rett fra
`custom_components/effektvakt/www/`. Bruk den framfor å legge testkort i en
produksjonsinstallasjon. Se `docs/dashboard-kort.md`.

---

## Deploye til lokal HA

Kopier `custom_components/effektvakt` til `/config/custom_components/` på HA-instansen og start på nytt. For rask iterasjon: monter config-mappen via Samba eller SSH.

```bash
rsync -av custom_components/effektvakt/ homeassistant:/config/custom_components/effektvakt/
```

---

## CI-workflows

`.github/workflows/ci.yml`:

- ruff check + format
- mypy
- pytest med coverage
- vulture (dead code)

`.github/workflows/validate.yml`:

- HACS validation (hassfest)
- manifest.json-sjekk

---

## Services

Effektvakt registrerer to tjenester:

### `effektvakt.set_safety_buffer`

Justerer sikkerhetsbufferen live uten restart.

```yaml
service: effektvakt.set_safety_buffer
data:
  kw: 1.5
```

### `effektvakt.reset_topp_3`

Nullstiller `daily_max_kw` for inneværende måned. Nyttig for testing eller hvis du vil starte over.

```yaml
service: effektvakt.reset_topp_3
```

---

## Diagnostics

HA-diagnostics er støttet. Eksporter diagnose fra **Settings > Devices & Services > Effektvakt > (device) > Download diagnostics**. Diagnose-filen inneholder koordinator-data, hysterese-state og kapasitetstrinn, men aldri sensor-entitet-ID-er (unngår persondata).
