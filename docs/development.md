# Utvikling

## Repo-struktur

```
custom_components/effektvakt/
    __init__.py         # Entry-setup, watchdog, service-registrering
    avlesning.py        # Effekt, energi og tidsstempel lest fra hass.states
    binary_sensor.py    # binary_sensor.effektvakt_kutt_ned_anbefalt
    brand/              # icon.png og icon@2x.png, generert (HA leser brand-bilder herfra)
    config_flow.py      # Config flow og options flow
    const.py            # Konstanter og default-verdier
    coordinator.py      # Ticket: kaller domenefilene, setter intervall, persist
    diagnostics.py      # HA diagnostics-support
    dso.py              # Kapasitetstrinn per nettselskap (generert)
    faceplate.py        # SVG-kilde for GEHA-METER-skiven (kort og trykk)
    frontend.py         # Statisk servering, Lovelace-ressurs, websocket-kommandoen
    hysterese.py        # HystereseState og apply_hysteresis
    laster.py           # Kuttbare laster per strategi, tilgjengelig kutt
    manifest.json       # HA integration manifest
    modell.py           # Terskelmodell, projeksjon, risiko, kostnad (ren Python)
    oppsett.py          # Trinn-tabellen en config entry faar, og hullene i den
    sensor.py           # De seks sensor-entitetene
    services.yaml       # Service-definisjoner
    strings.json        # Kildeteksten til oversettelsene
    switch.py           # switch.effektvakt_automatikk, hovedbryteren
    timeregnskap.py     # Timen: integrasjon, måleravstemming, dagsmaks, lagring
    translations/       # nb.json og en.json
    www/                # effektvakt-card.js, Lovelace-kortet

docs/
    bilder/             # Skjermbildene README og docs viser
    blueprints/         # Blueprint YAML-filer
    kort-harness/       # Prøvebenk for Lovelace-kortet, uten Home Assistant
    begrensninger.md
    beregninger.md
    blueprints.md
    dashboard-eksempel.yaml
    dashboard-kort.md
    development.md
    dso.md
    faq.md
    fysisk-panel.md
    input-sensorer.md
    oppsett.md
    sensorer.md
    strategi.md

esphome/
    effektvakt-panel.yaml   # ESP32-panelet, se fysisk-panel.md (ikke bygget)
    secrets.example.yaml

images/
    icon.svg            # Kilden til integrasjonsikonet

scripts/
    dso_kilder.json                   # Nøkkel, navn, prisområde og kilde per nettselskap
    export_faceplate.py               # Eksporter skiven til SVG for trykk og CAD
    generate_brand_images.py          # Rendre icon.svg til brand/-PNG-ene
    generer_dso_fra_fri_nettleie.py   # Skriver dso.py fra fri-nettleie-tariffene

tests/
    conftest.py
    fixtures/          # Timesforbruk for replay-testene, committet
    test_*.py
```

---

## Kjøre tester

Portene kjøres med [`just`](https://github.com/casey/just) og
[uv](https://docs.astral.sh/uv/). På macOS: `brew install just`, og uv fra
installasjonsscriptet deres. Ingenting installeres i system-Python, og
`pip install -e .` trengs ikke: `tests/conftest.py` legger
`custom_components/` på `sys.path` selv.

```bash
just                       # list oppskriftene
just test-unit             # hele suiten, tests/ med stubbet Home Assistant
just test-unit -k terskel  # ekstra argumenter går videre til pytest
just check                 # ruff check, ruff format --check, mypy, vulture
just test                  # test-unit + check, det som kreves før commit
just coverage              # coverage med terskel (feller under 90 %)
just fmt                   # formater, den eneste oppskriften som skriver
```

Oppskriftene er de samme kommandolinjene CI og pre-commit kjører. Er `just
check` grønn lokalt, er kvalitetsjobben i CI grønn på den samme commiten.

### Miljøene

Avhengighetene står som `[dependency-groups]` i `pyproject.toml` og er låst i
`uv.lock`. Hver gruppe får sitt eget venv, og ingen av dem deler `sys.modules`:

| Gruppe       | Miljø              | Python | Innhold                                      |
| ------------ | ------------------ | ------ | -------------------------------------------- |
| `unit`       | `.venv-unit`       | 3.13   | `tests/` med stubbet Home Assistant          |
| `kvalitet`   | `.venv-kvalitet`   | 3.13   | ruff, mypy, vulture, pre-commit              |
| `ha-minimum` | `.venv-ha-minimum` | 3.13   | ekte HA 2025.1.0, det `hacs.json` lover      |
| `ha-current` | `.venv-ha-current` | 3.14   | ekte HA 2026.9.2                             |

De to HA-gruppene er løst i `uv.lock` og venter på `tests_ha/`. Verktøyene i
`kvalitet` er pinnet eksakt til de samme versjonene `.pre-commit-config.yaml`
bruker; sprik der viser seg som at formateringen endrer seg av seg selv.

### DSO-tabellen

```bash
just dso-hent               # hent fri-nettleie på pinnet commit til _fri-nettleie/
just dso-sjekk _fri-nettleie  # samme sjekk som CI, uten nett
just dso-sjekk              # uten utsjekk: laster ned tariffene selv
```

---

## Pre-commit hooks

```bash
pre-commit install
pre-commit install --hook-type pre-push
pre-commit run --files <filene dine>
```

Hookene kjører ruff (lint og format), vulture, mypy og de vanlige
whitespace-, JSON- og YAML-sjekkene. `mypy` er blokkerende, både her og i CI.
DSO-hooken er `files`-gatet på `dso.py`, generatoren og `dso_kilder.json`, så
den kjører bare når du rører dem. `pytest` henger på `pre-push` og kaller
`just test-unit`, altså nøyaktig den samme kommandolinjen som CI.

Flere agenter jobber i det samme treet, så kjør `pre-commit run --files` med
dine egne filer framfor `--all-files`.

---

## Oppdatere DSO-data

`custom_components/effektvakt/dso.py` er generert fra tariffilene i
[kraftsystemet/fri-nettleie](https://github.com/kraftsystemet/fri-nettleie) (CC-BY-4.0), pinnet til
commiten som står i `scripts/dso_kilder.json`. Slik tar du inn nye satser:

```bash
# 1. sett _meta.commit og _meta.tariff_dato i scripts/dso_kilder.json
# 2. regenerer
python3 scripts/generer_dso_fra_fri_nettleie.py
# 3. les diffen, kjør testene, commit dso.py og dso_kilder.json
python3 -m pytest tests/test_dso_data.py
```

Scriptet laster ned tariffene selv. Har du en utsjekk av fri-nettleie, gir `--kilde <sti>` samme
resultat uten nett, og det er den varianten CI bruker. `--check` feller hvis `dso.py` ikke er
nøyaktig det generatoren ville skrevet. Se [dso.md](dso.md) for formatet og for de to
nettselskapene som ikke følger NVE-modellen.

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

`.github/workflows/ci.yml` kjører på PR mot `main`, på push til `main`, og som
`workflow_call` fra release-maskineriet. Fire jobber pluss en port:

- **test-unit**: sjekker at replay-fixturene faktisk finnes (de lå som symlink
  og skippet seg selv stille fram til september 2026), kjører `just
  coverage-unit` og `just coverage-gate`, og laster opp til Codecov. Codecov
  er `continue-on-error`: dekning skal ikke avgjøre om CI er grønn, terskelen
  håndheves av `coverage-gate`.
- **check**: `just check`, altså ruff check, `ruff format --check`, mypy og
  vulture. Deretter DSO-tabellen mot en utsjekk av fri-nettleie på commiten i
  `scripts/dso_kilder.json`, at `manifest.json` er gyldig JSON med
  semver-versjon, at den versjonen er den samme som i `pyproject.toml`, og at
  de påkrevde filene finnes.
- **hacs** og **hassfest**: de to valideringene. De ligger her og ikke bare i
  `validate.yml` fordi release-porten ikke kan vente på noe den ikke ser.
- **release-gate**: feller når en av de fire ikke er `success`. `skipped` og
  `cancelled` teller som feil, siden en jobb som ikke kjørte ikke har sagt at
  noe er i orden. Det er denne jobben grenbeskyttelsen og release-flyten skal
  kreve grønn.

Mypy er blokkerende. Den var rådgivende med `|| true` fram til september 2026,
og det den samlet opp i mellomtiden var 26 feil ingen så.

`.github/workflows/validate.yml` kjører HACS-valideringen og hassfest om igjen
hver natt, pluss på `workflow_dispatch`. Begge kan bli røde av endringer
utenfor repoet, og det vil vi vite før neste release.

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
