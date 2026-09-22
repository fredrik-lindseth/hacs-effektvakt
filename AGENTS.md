# AGENTS.md

Home Assistant-integrasjon som projiserer time-snittet ditt og sier fra før
timen dytter deg opp i et dyrere kapasitetstrinn i nettleien. Norske
strømkunder, NVE-modellen for kapasitetsledd.

Integrasjonen er ikke sluppet. Ingen tagger, ingen releases, CHANGELOG sier
«Pre-release», og Fredrik er eneste bruker. Brytende endringer koster ingenting
akkurat nå: bytt datamodell, entitets-id-er og lagringsformat mens det er
gratis, framfor å bygge migreringsstier for brukere som ikke finnes.

## Samtidighet: flere agenter i samme arbeidstre

Flere agenter committer i det samme arbeidstreet samtidig. Det har alt gått
galt en gang, så reglene er ufravikelige:

- Aldri `git add -A`, aldri `git commit -a`. Alltid eksplisitt pathspec med
  bare de filene du eier.
- Aldri `git commit --amend`, `git rebase` eller `git reset`. Du kan rydde i
  en annens commit uten å vite det.
- `pre-commit run --files <dine filer>`, ikke `--all-files`. Sistnevnte
  formaterer og retter filer andre holder på med.
- Ikke push med mindre du er bedt om det.

Ser du endringer i `git status` du ikke har gjort, er det noen andre. La dem
være.

## Kritiske regler

1. **`custom_components/effektvakt/dso.py` er autogenerert** fra
   [fri-nettleie](https://github.com/kraftsystemet/fri-nettleie). Rediger den
   aldri for hånd. `python3 scripts/generer_dso_fra_fri_nettleie.py`
   regenererer, `--check` feiler på diff, og CI kjører `--check`. Uten
   `--kilde` lastes tarballen ned på commiten som er pinnet i
   `scripts/dso_kilder.json`; `--kilde <sti>` eller `$FRI_NETTLEIE_ROOT` peker
   på en utsjekk.
2. **Nøklene eies av oss, prisene av fri-nettleie.** `scripts/dso_kilder.json`
   bestemmer hvilke nettselskap som finnes, fordi nøklene ligger i folks
   config entries og aldri kan slettes. `tests/test_dso_data.py` har et frosset
   nøkkelsett som blokkerer sletting og tillater nye. Skal et nettselskap inn,
   legges det der med slug og mva-sone, ikke i `dso.py`.
3. **Topp-3-regelen er domenet, og den bor i `modell.py`.** Nettselskapet
   fakturerer snittet av de tre høyeste time-snittene fra tre ulike dager i
   måneden. En enkelt time over terskelen koster ikke trinnet i seg selv: den
   må dra snittet av de tre over. Er dagens topp allerede blant de tre høyeste,
   er en ny time på samme nivå gratis.

   `custom_components/effektvakt/modell.py` er hele terskelaritmetikken, ren
   Python uten HA-import, og risiko, margin, kostnad og «kan legge på» regner
   alle fra det samme taket. Kjeden er: `minste_mulige_topp_3_kw` (sum av
   inntil tre dagsmaks delt på tre) gir måltrinnet `T`, `dagstak_kw` er
   `min(T, 3T - de to høyeste ANDRE dagene)`, og `time_tak_kw` er
   `max(dagens maks, dagstak)`. **Jo høyere de andre dagene er, jo lavere er
   grensen for hva dagen i dag tåler.** Koden gjorde det motsatt fram til
   september 2026, og feilen overlevde fordi testene kodet inn den samme
   antakelsen. Legger du til en terskel, legg den her og la coordinatoren
   kalle, ellers får integrasjonen to svar på det samme spørsmålet igjen.
   Tester i `tests/test_terskelmodell.py`, utledningen i
   `docs/beregninger.md`.
4. **Hysterese-invarianten**: oppgang i risiko er umiddelbar, nedgang krever
   holdetid, og flere trinn ned tas ett om gangen med ny timer per trinn.
   `apply_hysteresis` i `hysterese.py`, tester i `tests/test_hysteresis.py`.
   Bryter du dette, slår varmtvannsberederen av og på i takt med en støyete
   effektsensor.
5. **Watchdog-kontrakten**: henger coordinatoren i mer enn
   `WATCHDOG_STALE_THRESHOLD_SECONDS` (120), setter watchdogen sensorene til
   `unknown`. Sjekken kjører hvert minutt fra `async_setup_entry`.
   Automasjoner og blueprints regner med at `unknown` betyr «vet ikke», ikke
   «alt er fint».
6. **Failsafe-regelen i blueprintene**: hver blueprint som styrer last slipper
   den ved neste timeskifte, uavhengig av hva Effektvakt sier, fordi verdien av
   et kutt slutter der. `max_off_minutes` er bare nødbremsen hvis timeskiftet
   uteblir, og `min_on_minutes` krever at lasten har stått på en stund før den
   kan kuttes igjen i den nye timen.
   Hovedbryteren `switch.effektvakt_automatikk` stopper nye kutt, men avbryter
   aldri en failsafe-timer som alt går. Fjerner du den grenen, kan en
   varmtvannsbereder bli stående av i det uendelige.
7. **Repoet er norsk.** Kode, kommentarer, docs og commit-meldinger på norsk,
   uformelt bokmål uten a-endinger. Docstrings og kommentarer i Python-filene
   bruker aa/oe/aa-translitterasjon enkelte steder; følg filen du er i framfor
   å normalisere.

## Arkitektur

Fire lag. Filnavnene under er kartet, og `docs/development.md` har
repo-strukturen i sin helhet.

- **Entry-livssyklus og frontend**: `__init__.py` (setup, watchdog,
  tjenesteregistrering, opplasting), `frontend.py` (serverer kortet på
  `/effektvakt-static`, melder URL-en inn i Lovelace sitt ressursregister,
  websocket-kommandoen som leverer skiven), `config_flow.py` (config flow og
  options flow, sensorvalidering).
- **Domene**: fem filer uten en eneste HA-import, så de kan regnes og testes
  uten stubber. `modell.py` har topp-3-aritmetikken, terskelmodellen,
  projeksjonen, risikoklassifiseringen og kostnaden. `timeregnskap.py` eier
  timen: trapesintegrasjon, avstemming mot måleren, den ventende timen over
  timeskiftet, dagsmaks, månedsrullering og lagringsformatet.
  `hysterese.py` er `HystereseState` og `apply_hysteresis`. `laster.py` er de
  kuttbare lastene og `compute_tilgjengelig_kutt_kw`. `oppsett.py` slår opp
  trinn-tabellen en config entry faktisk får, og navngir hullene i den.
- **Drift**: `coordinator.py` er ticket, ikke regnestykket. Den leser config
  entry, henter sensorverdier gjennom `avlesning.py`, mater `Timeregnskap`,
  spør `modell.py`, `laster.py` og `hysterese.py`, setter tick-intervallet og
  skriver tilstanden til `Store`. `avlesning.py` er den eneste andre filen som
  rører `hass.states`. Legg ny logikk som en fri funksjon, ikke som en metode,
  og legg den i domenelaget hvis den er ren regning.
- **Entiteter**: `sensor.py` (seks sensorer), `binary_sensor.py`
  (`binary_sensor.effektvakt_kutt_ned_anbefalt`), `switch.py` (hovedbryteren),
  `diagnostics.py`.

`faceplate.py` er kilden til GEHA-METER-skiven, og både Lovelace-kortet og
trykkvarianten til det fysiske panelet kommer fra den samme SVG-generatoren.
Tegner du skiven på nytt i JavaScript, drifter de fra hverandre. Panelet selv
er en skisse som ikke er bygget, se statusboksen i `docs/fysisk-panel.md`.

## Hovedfiler

| Fil                                          | Innhold                                                                                   |
| -------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `custom_components/effektvakt/__init__.py`   | Entry-setup og -unload, watchdog-timer, de to tjenestene, `CONFIG_SCHEMA`                  |
| `custom_components/effektvakt/coordinator.py`| Ticket: leser config entry, kaller domenefilene, setter tick-intervall, persisterer til `Store` |
| `custom_components/effektvakt/avlesning.py`  | Effekt-, energi- og tidsstempelavlesning fra `hass.states`, med enhet og klamp             |
| `custom_components/effektvakt/timeregnskap.py`| `Timeregnskap`: integrasjon, måleravstemming, ventende time, dagsmaks, månedsrullering, lagringsformat |
| `custom_components/effektvakt/modell.py`     | Terskelmodellen, projeksjonen, risikoklassifiseringen og kostnaden. Ren Python, se regel 3 |
| `custom_components/effektvakt/hysterese.py`  | `HystereseState` og `apply_hysteresis`, se regel 4                                         |
| `custom_components/effektvakt/oppsett.py`     | Trinn-tabellen en config entry får, ukjent DSO-nøkkel og manglende topptrinn                |
| `custom_components/effektvakt/laster.py`     | Kuttbare laster fra config entry, `compute_tilgjengelig_kutt_kw` og migreringen fra strategi |
| `custom_components/effektvakt/const.py`      | Risiko-nivåer og rangering, tick-intervaller, watchdog-terskler, legacy-mapping, klamper   |
| `custom_components/effektvakt/config_flow.py`| Config flow og options flow, validering av effekt- og energisensor                         |
| `custom_components/effektvakt/dso.py`        | Kapasitetstrinn per nettselskap. AUTOGENERERT, se regel 1                                  |
| `custom_components/effektvakt/faceplate.py`  | SVG-kilden til skiven, delt av kortet og trykkfilen                                        |
| `custom_components/effektvakt/frontend.py`   | Statisk servering, Lovelace-ressurs med cache-buster, websocket-kommandoen `effektvakt/faceplate` |
| `custom_components/effektvakt/www/`          | `effektvakt-card.js`, selve Lovelace-kortet. Serveres uten innlogging                      |
| `custom_components/effektvakt/sensor.py`     | De seks sensorene, entitets-id-ene og unique_id-ene                                        |
| `custom_components/effektvakt/binary_sensor.py` | Kutt-anbefalingen automasjoner trigger på                                               |
| `custom_components/effektvakt/switch.py`     | `switch.effektvakt_automatikk`, hovedbryteren                                              |
| `docs/blueprints/`                           | De fire blueprintene brukeren importerer for hånd                                          |
| `docs/kort-harness/server.py`                | Prøvebenk for kortet, uten Home Assistant                                                  |
| `scripts/generer_dso_fra_fri_nettleie.py`    | Regenererer `dso.py` fra fri-nettleie, `--check` i CI                                      |
| `scripts/dso_kilder.json`                    | Nøkkel, navn, prisområde, fri-nettleie-slug og mva-sone per nettselskap                    |
| `scripts/export_faceplate.py`                | Skiven til SVG for trykk og CAD                                                            |
| `scripts/generate_brand_images.py`           | Rendrer `images/icon.svg` til `brand/`-PNG-ene, `--sjekk` feiler på utdaterte              |

## Porter

Portene kjøres med `just` og uv. Ingenting installeres i system-Python.

```bash
just test-unit               # tests/ med stubbet Home Assistant
just check                   # ruff check, ruff format --check, mypy, vulture
just test                    # begge, det som kreves før commit
just test-ha minimum         # tests_ha/ mot ekte HA 2025.1.0, det hacs.json lover
just test-ha current         # tests_ha/ mot ekte HA 2026.9.2
just coverage                # begge suitene slått sammen, feller under 95 %
pre-commit run --files <filene dine>
```

Oppskriftene i `justfile` er de samme kommandolinjene CI og pre-commit kjører,
så en rød port kan reproduseres lokalt. `tests/test_testkommandoer.py` feller
når justfile, denne filen, `docs/` og `ci.yml` ikke lenger sier det samme om
kommandoene.

`just test` krever ikke Home Assistant og er det som skal være grønt før hver
commit. Ekte-HA-testene er tyngre og henger på CI, men begge målene skal være
grønne: feller `minimum`, er det enten en kompatibilitetsfeil å rette eller et
minimum å heve med vilje.

`tests/` og `tests_ha/` kan ikke dele miljø. `tests/conftest.py` stubber
`homeassistant.*` i `sys.modules`, og en ekte homeassistant ved siden av ville
kollidert med stubbene. Derfor står avhengighetene som fire `[dependency-groups]`
i `pyproject.toml`, låst i `uv.lock`, med ett venv per gruppe.
`docs/development.md` har tabellen over miljøene.

Pre-commit kjører ruff (lint og format), vulture, mypy og de vanlige
whitespace-/JSON-/YAML-sjekkene. `pytest` henger på `pre-push`, ikke på
`pre-commit`, og kaller `just test-unit`. **Mypy er blokkerende** her og i CI
fra september 2026. Den var rådgivende med `|| true`, og det den samlet opp i
mellomtiden var 26 feil ingen så.

DSO-hooken «DSO-tabell mot fri-nettleie» er grønn og skal holdes grønn. Den er
`files`-gatet på `dso.py`, generatoren og `dso_kilder.json`, så den kjører bare
når du rører dem. CI kjører den samme sjekken ubetinget, mot en utsjekk av
fri-nettleie på commiten i `dso_kilder.json`.

`ruff-format`-hooken er pinnet til `v0.16.8`, samme versjon som ligger lokalt,
så `ruff format --check` og pre-commit brekker linjer likt. `line-length` er 120
i `pyproject.toml`, og E501 er slått av i ruff-lint.

CI (`.github/workflows/ci.yml`) har seks jobber og en port: `test-unit`
(fixtur-vakt, `just coverage-unit`, Codecov), `test-ha` (matrise over
`minimum` og `current`, `fail-fast: false`, så svaret «begge ryker» skilles fra
«bare den ene»), `coverage` (venter på begge suitene, henter datafilene deres
og kjører `just coverage-gate`), `check` (`just check`, DSO-sjekken mot
fri-nettleie på pinnet commit, manifest-validering og versjonssynk mot
`pyproject.toml`), `hacs` og `hassfest`. `release-gate` feller når en av dem
ikke er `success`; `skipped` teller som feil. `validate.yml` kjører HACS og
hassfest om igjen nattlig.

Coverage-terskelen er 95 % på summen av de to suitene, ikke på hver av dem for
seg: hver av dem lar kode stå udekket som den andre dekker. Den sto på 90 fram
til `tests_ha/` kom og dekket `config_flow.py`, `frontend.py` og
`diagnostics.py`.

`manifest.json` og `pyproject.toml` skal ha den samme versjonen.
Check-jobben feller ved sprik, så bump begge i samme commit.

## Fallgruver

1. **`www/` kan ikke hete `frontend/`.** Modulen `frontend.py` ligger i samme
   pakke, og en katalog med det navnet ville skygget for den så snart den fikk
   en `__init__.py`. Forklart i `const.py` ved `FRONTEND_DIR_NAME`.
2. **Cache-busteren på kortet er nødvendig.** Kort-URL-en meldes inn som
   `...effektvakt-card.js?v=<manifestversjon>`. Uten `?v=` serverer nettleseren
   forrige versjon av kortet etter en oppdatering. `_kort_url` i `frontend.py`.
3. **Lovelace-ressursregisteret, ikke `add_extra_js_url`.** `add_extra_js_url`
   legger bare et `import()` ingen venter på, så uten varm cache rakk aldri
   kortet å definere seg før viewet ble tegnet, og begge kortene kom opp som
   «Konfigurasjonsfeil». `add_extra_js_url` er reserveveien når Lovelace kjører
   med YAML-ressurser, og det skal aldri være to veier inn til den samme filen:
   `customElements.define` kaster på andre innlasting.
4. **Ressursregisteret deles med HACS og brukeren.** Skriv bare når noe faktisk
   har endret seg, rydd duplikater, og ta oppføringen ut igjen i
   `async_remove_entry`.
5. **Registreringen er idempotent med vilje.** `async_register_frontend` kalles
   både fra `async_setup` og fra `async_setup_entry`, fordi `async_setup` aldri
   kjører igjen hvis brukeren fjerner og legger til oppsettet uten omstart.
6. **Tjenestene er domenetjenester uten mål**, registrert én gang og fjernet
   først når siste entry er lastet ut. `entry.runtime_data` nulles i
   `async_unload_entry` nettopp fordi `_loaded_coordinators` teller på den.
7. **Månedsrulleringen kommer etter måleravstemmingen.** En avlesning som
   retter den siste timen i måneden skal inn i topp-3-en som arkiveres, ikke
   lande i den ferske måneden. Rekkefølgen står i `_async_update_data` i
   `coordinator.py`.
8. **Effektankeret overlever en kort omstart.** Hele timetilstanden persisteres
   til `Store` (`effektvakt_<entry_id>`): akkumulert kWh, timestart, siste
   målerstand med tidspunkt, siste effekt med tidspunkt, dekningsvinduet og
   hysterese-tilstanden. Formatet eies av `Timeregnskap.til_lagring` og
   `.fra_lagring` i `timeregnskap.py`, og `coordinator.py` legger bare
   hysteresen ved siden av. Legger du til felt, husk at eldre lagring mangler
   dem; `_les_siste_maalerstand` i `timeregnskap.py` viser mønsteret for å
   hente verdien ut av det gamle formatet framfor å kaste den.
9. **Målehull er et ærligere svar enn et anslag.** Går det mer enn
   `MAX_INTEGRATION_GAP_H` (5 minutter, definert i `timeregnskap.py`) mellom to
   tick, har HA vært nede, og trapesintegrasjonen hopper over vinduet.
   Energimåleren fyller det ved neste avlesning.
10. **Risiko-verdiene er kontrakt.** Strengene i `RISIKO_LEVELS` står i
    automasjoner, i loggen og i utviklerverktøyene. Rekkefølgen i listen er
    terskelen `min_risiko_for_kutt` sammenlignes etter, så flytter du en verdi,
    flytter du terskelen for alle som har valgt den. `LEGACY_RISIKO_MAPPING`
    holder gamle lagrede verdier i live; ikke fjern den uten å vite at ingen
    har dem på disk.
11. **`unique_id` er låst av entitetsregisteret.** Både sensorene,
    binary-sensoren og switchen bygger den av `entry_id` pluss en nøkkel.
    Endrer du nøkkelen, får brukeren en ny entitet og mister historikken.
12. **Hovedbryteren stopper bare kutt.** Sensorene regner videre uansett, så
    projeksjon, risiko og kostnad er like sanne med vakten av. Grenene som
    slår last på igjen er ikke gatet av bryteren, ellers kunne en
    varmtvannsbereder blitt stående av fordi noen vippet bryteren midt i et
    kutt.
13. **Brand-PNG-ene redigeres aldri for hånd.** De genereres fra
    `images/icon.svg` og bærer SHA-256-en av kilden i en tEXt-chunk, så
    `tests/test_brand_images.py` kjenner igjen en utdatert PNG.
14. **Diagnostics skal aldri lekke entitets-id-er.** Filen inneholder
    koordinatordata, hysterese-tilstand og kapasitetstrinn, men ikke hvilke
    sensorer brukeren har pekt på.

## Home Assistant hos Fredrik

`ssh ha-local` (192.168.1.142) er Fredriks egen Home Assistant. **Det er
produksjon, ikke et testmiljø.** Den styrer ekte last i huset, og et uhell der
merkes av folk som ikke sitter i denne økten.

- Ta en tidsstemplet sikkerhetskopi før du rører noe, og la kopien ligge.
- Ikke opprett dashbord, views, automasjoner eller packages der. Det er
  Fredriks oppsett, ikke en sandkasse.
- Skal kortet prøves, bruk prøvebenken:
  `python3 docs/kort-harness/server.py`. Den serverer den ekte kortfilen fra
  `custom_components/effektvakt/www/` med skiver generert fra `faceplate.py`,
  uten at Home Assistant er involvert.
- Trengs en deploy likevel, er det `rsync` av `custom_components/effektvakt/`
  til `/config/custom_components/effektvakt/` og en omstart. Legg tilbake
  etterpå hvis versjonen ikke var ment å bli stående.

## Issue-tracking

Namespace i dcat er `hacs-effektvakt`, avledet av repo-navnet. Repoet har
verken `.dogcatrc` eller `.dogcats/`, så dcat faller tilbake til
`default_storage` i `~/.config/dogcat/config.toml`. Det virker, og det er med
vilje: ingen issue-data skal committes hit.

`dcat ready` viser backloggen. GitHub Issues er kun for eksterne
brukerrapporter; de besvares og lukkes der, men arbeidet de utløser føres i
dcat.

Fra et git-worktree kjøres dcat alltid med `-C <hovedutsjekk>`, ellers avledes
namespacet av worktree-katalogens navn.

## Dokumentasjon

`docs/development.md` er utvikler-guiden og har repo-strukturen,
eksport-scriptene, ikon-regenereringen og tjenestene i full lengde. Lenk dit
framfor å duplisere.

| Dokument                                         | Innhold                                  |
| ------------------------------------------------ | ---------------------------------------- |
| [docs/development.md](docs/development.md)       | Utvikler-guide, scripts, arkitektur      |
| [docs/beregninger.md](docs/beregninger.md)       | Formler og beregningslogikk              |
| [docs/sensorer.md](docs/sensorer.md)             | Sensorer og attributter                  |
| [docs/input-sensorer.md](docs/input-sensorer.md) | Hva integrasjonen trenger som input      |
| [docs/oppsett.md](docs/oppsett.md)               | Konfigurasjonsflyten steg for steg       |
| [docs/laster.md](docs/laster.md)                 | Kuttbare laster og tilgjengelig kutt     |
| [docs/blueprints.md](docs/blueprints.md)         | Import, input, failsafe-garantien        |
| [docs/dashboard-kort.md](docs/dashboard-kort.md) | Lovelace-kortet, stiler og merker        |
| [docs/fysisk-panel.md](docs/fysisk-panel.md)     | ESP32-panel med ekte viser, ikke bygget  |
| [docs/dso.md](docs/dso.md)                       | DSO-data og oppdatering                  |
| [docs/begrensninger.md](docs/begrensninger.md)   | Kjente begrensninger                     |
| [docs/faq.md](docs/faq.md)                       | Ofte stilte spørsmål                     |

## Vanlige oppgaver

- **Legge til et nettselskap**: legg nøkkel, navn, prisområde, fri-nettleie-slug
  og mva-sone i `scripts/dso_kilder.json`. Deretter
  `python3 scripts/generer_dso_fra_fri_nettleie.py` og commit `dso.py`.
- **Endre en beregning**: legg den som en fri funksjon i `modell.py` med egen
  test i `tests/`, framfor å utvide `_async_update_data`. Handler den om timen
  som bygges opp, hører den i `timeregnskap.py`; trenger den å lese sensorer,
  i `avlesning.py`. `coordinator.py` skal bare kalle.
- **Endre skiven**: `faceplate.py` er eneste kilde. Prøv i
  `docs/kort-harness/server.py`, og sjekk trykkvarianten med
  `python3 scripts/export_faceplate.py --dso bkk --variant card --png`.
- **Endre ikonet**: rediger `images/icon.svg`, kjør
  `python3 scripts/generate_brand_images.py`, og døm resultatet i 24 og 48
  piksler i både lys og mørk bakgrunn før du tror på det.
- **Legge til en tjeneste**: handler i `_async_register_services` i
  `__init__.py`, felt i `services.yaml`, og husk at den virker på alle lastede
  entries.
