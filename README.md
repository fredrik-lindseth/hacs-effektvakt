# Effektvakt

Norsk · [English](README.en.md)

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest"><img src="https://img.shields.io/github/v/release/fredrik-lindseth/hacs-effektvakt" alt="Release"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/ci.yml"><img src="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/validate.yml"><img src="https://github.com/fredrik-lindseth/hacs-effektvakt/actions/workflows/validate.yml/badge.svg" alt="HACS Validation"></a>
  <a href="https://app.codecov.io/gh/fredrik-lindseth/hacs-effektvakt"><img src="https://codecov.io/gh/fredrik-lindseth/hacs-effektvakt/branch/main/graph/badge.svg" alt="Codecov"></a>
</p>

Effektvakt regner ut hvor høyt time-snittet ditt ender, og sier fra i tide hvis timen er på vei til å dytte deg opp i et dyrere kapasitetstrinn i nettleien. Integrasjon for Home Assistant, laget for norske strømkunder.

## Et regneeksempel fra BKK

1 kW lavere topp-3-snitt ville redusert kapasitetsleddet med 165 kr i desember 2025 og 165 kr i februar 2026 i et BKK-anlegg: til sammen 330 kr. 600 W ville ikke vært nok til å nå det billigere trinnet. Dette er et beregnet potensial fra historiske timesdata; lasten må gå lenge nok, og utsatt oppvarming må få plass senere. Se [regnestykket og simuleringen](docs/sparepotensial.md) og [en eksempelrapport for lastprofiler](docs/research/lastprofil-rapport.md).

<p align="center">
  <img src="docs/bilder/skive-gossen.png" alt="Effektvakt-kortet: en gjenskapt analog effektvakt med kW-skala, kapasitetstrinn med månedspris, og tre visere" width="420">
</p>

## Hvordan det virker

Effektvakt projiserer timegjennomsnittet og sammenligner det med månedens kapasitetstrinn. Sensorene viser margin, risiko, topp-3-snitt og målt tilgjengelig kutt akkurat nå. Du kan bruke varsler eller blueprints til å styre bereder, oppvarming og andre laster. Lastvernet kobler styrte laster inn igjen innen fristen og husker ansvaret gjennom reload og omstart.

Beregningen støtter tariffer med de tre høyeste timegjennomsnittene fra ulike dager. Husholdningstariffer følger med; egendefinerte trinn må bruke samme metode. Manglende eller gamle effektmålinger gir ukjent råd. [Strømkalkulator](https://github.com/fredrik-lindseth/hacs-strømkalkulator) beregner nettleie, avgifter og støtteordninger. Et unngått kapasitetstrinn sparer kroner uten nødvendigvis å redusere kWh. Prisplanlegging fra Nord Pool er ikke implementert.

Oppsett, entiteter og kort støtter norsk og engelsk. Veiledningene om sparepotensial og lastprofiler finnes på begge språk; øvrig detaljdokumentasjon er på norsk.

## Installasjon

Krever Home Assistant 2025.1.0 eller nyere.

### HACS

1. Åpne menyen i HACS og velg **Custom repositories**.
2. Legg til `https://github.com/fredrik-lindseth/hacs-effektvakt` med typen **Integration**.
3. Last ned **Effektvakt** og start Home Assistant på nytt.

### Manuell installasjon

Last ned `effektvakt.zip` fra [siste release](https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest) og pakk den ut i `/config/custom_components/effektvakt`. Start Home Assistant på nytt.

Deretter **Settings > Devices & Services > Add Integration > Effektvakt**. Du velger nettselskap, peker på power-sensoren din, og resten har standardverdier som duger. Stegene er beskrevet i [docs/oppsett.md](docs/oppsett.md).

## Dashbord og laststyring

Legg `custom:effektvakt-card` til i dashbordet; se [kortoppsettet](docs/dashboard-kort.md). Rød viser er projisert timegjennomsnitt, den tynne svarte er effekten akkurat nå, og trekanten utenfor buen er månedens topp-3-snitt.

<p align="center">
  <img src="docs/bilder/dashboard.png" alt="Dashbord med effektskive, kort for resten av timen og ukesgraf" width="900">
</p>

Registrer de kuttbare lastene under Konfigurer og importer [blueprintene](docs/blueprints.md) for varsling eller automatisk lastkutt. Velg maksimal utkobling og minste påtid etter hva lasten tåler. [Veiledningen om lastprofiler](docs/lastprofiler.md) forklarer hvordan du anslår bidraget resten av timen.

## Kvalitet og utvikling

CI tester lovet minimum og aktuell Home Assistant-versjon, validerer HACS og hassfest og krever 95 % samlet testdekning. [Codecov](https://app.codecov.io/gh/fredrik-lindseth/hacs-effektvakt) viser rapportene. Miljøer og kommandoer står i [utviklerguiden](docs/development.md).

## Dokumentasjon

| Dokument                                           | Innhold                            |
| -------------------------------------------------- | ---------------------------------- |
| [Sparepotensial](docs/sparepotensial.md) | Månedsmål og historisk simulering |
| [Lastprofiler](docs/lastprofiler.md) | Metode, lokal analyse og tolkning |
| [Målerapport](docs/research/lastprofil-rapport.md) | Kunstig eksempel og rapportmal |
| [docs/oppsett.md](docs/oppsett.md)                 | Konfigurasjonsflyten steg for steg |
| [docs/sensorer.md](docs/sensorer.md)               | Alle sensorer og attributter       |
| [docs/beregninger.md](docs/beregninger.md)         | Formler og beregningslogikk        |
| [docs/input-sensorer.md](docs/input-sensorer.md)   | Sensorkrav og kjente kilder        |
| [docs/laster.md](docs/laster.md)                   | Kuttbare laster og terskler        |
| [docs/blueprints.md](docs/blueprints.md)           | Import, input og eksempler         |
| [docs/dashboard-kort.md](docs/dashboard-kort.md)   | Lovelace-kortet                    |
| [docs/fysisk-panel.md](docs/fysisk-panel.md)       | ESP32-panel, skisse (ikke bygget)  |
| [docs/begrensninger.md](docs/begrensninger.md)     | Kjente begrensninger               |
| [docs/dso.md](docs/dso.md)                         | DSO-data og oppdatering            |
| [docs/development.md](docs/development.md)         | Utvikler-guide                     |
| [docs/faq.md](docs/faq.md)                         | Ofte stilte spørsmål               |

## Lisens

MIT. Se [LICENSE](LICENSE).
