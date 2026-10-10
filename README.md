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

I timesdata fra et BKK-anlegg var månedens topp-3-snitt 5,823 kW i desember 2025 og 5,702 kW i februar 2026. Begge månedene kostet kapasitetstrinnet 415 kr. Hvis laststyring hadde redusert topp-3-snittene med 1 kW, ville de blitt 4,823 og 4,702 kW. Da ville kapasitetsleddet kostet 250 kr per måned: 165 kr mindre i hver måned, til sammen 330 kr.

600 W reduksjon i topp-3-snittene ville gitt 5,223 og 5,102 kW. Det er fortsatt over 5 kW og gir ingen reduksjon i kapasitetsleddet. Hvor mye last du kan kutte, og hvor lenge, avgjør om du kommer ned et trinn.

Dette er et beregnet potensial fra [historiske timesdata](tests/fixtures/README.md), ikke en målt besparelse fra automatisk styring. Lasten må faktisk være på og kunne kobles ut lenge nok. Utsatt oppvarming eller lading må også få plass senere uten å lage nye topper. Effektvakt viser når et lastkutt kan påvirke kapasitetsleddet og lar deg varsle eller styre lastene med blueprints.

<p align="center">
  <img src="docs/bilder/skive-gossen.png" alt="Effektvakt-kortet: en gjenskapt analog effektvakt med kW-skala, kapasitetstrinn med månedspris, og tre visere" width="420">
</p>

## Hvordan det virker

De fleste norske nettselskap fakturerer kapasitetsleddet etter snittet av de tre høyeste time-snittene fra ulike dager i måneden (NVE-modellen). Drar én time snittet av de tre over neste terskel, betaler du det høyere trinnet for hele måneden, uansett hvor lite du bruker resten av tiden.

Motsatt vei gjelder også: er dagens topp allerede blant de tre høyeste, koster en ny time på samme nivå ingenting.

Effektvakt leser power- og energy-sensoren din hvert 15-60 sekund og projiserer hva time-snittet blir ved time-slutt, ut fra hva som er brukt så langt og hva som brukes akkurat nå. Marginen måles mot terskelen for neste trinn, justert for hvilke av topp-3-dagene som allerede er registrert denne måneden. Risiko-nivået har hysterese, så en kortvarig dipp slår ikke lasten av og på igjen med det samme.

Bare denne topp-3-metoden er støttet. Sør Aurdal Energi (månedsmaks) og Tinfos (uverifisert metode) er sperret for styringsråd; se [tariffgrunnlaget](docs/dso.md). Manglende eller mer enn to minutter gamle effektmålinger gir ukjent råd, ikke ledig kapasitet. Tid og timegrenser regnes i UTC, slik at de to 02-timene om høsten holdes atskilt.

Effektvakt eier varsling og styring av laster for å redusere forbruk og kostnader. Dagens funksjoner gjelder kapasitet; prisplanlegging fra Nord Pool er ikke implementert. [Strømkalkulator](https://github.com/fredrik-lindseth/hacs-strømkalkulator) beregner nettleie, avgifter og støtteordninger. Unngått kapasitetstrinn er spart kostnad, og betyr ikke i seg selv færre kWh.

De innebygde tabellene gjelder husholdning. Har fritidsboligen en annen tariff, bruk egendefinerte topp-3-trinn fra nettselskapets prisliste.

## Hva du får

- Projisert time-snitt, margin til neste trinn og topp-3-snitt for måneden, som sensorer
- Risiko for neste trinn (god margin, nærmer seg, like under, over terskelen) og en binary sensor som automations kan trigge på
- Anslag på hvor mye du faktisk har å kutte, summert fra lastene du har lagt inn
- Fire blueprints for varmtvannsbereder, panelovner og varsler
- Lagret gjeninnkoblingsansvar og minste påtid som overlever automasjons-reload og HA-omstart; utilgjengelige laster forsøkes gjenopprettet når de svarer igjen
- Et Lovelace-kort som tegner skiven fra dine egne kapasitetstrinn
- Watchdog som setter sensorene til `unknown` hvis coordinatoren henger

Oppsett, entiteter og kort støtter norsk og engelsk. Detaljdokumentasjonen nedenfor er foreløpig på norsk.

## Installasjon

Krever Home Assistant 2025.1.0 eller nyere.

### HACS

1. Åpne menyen i HACS og velg **Custom repositories**.
2. Legg til `https://github.com/fredrik-lindseth/hacs-effektvakt` med typen **Integration**.
3. Last ned **Effektvakt** og start Home Assistant på nytt.

### Manuell installasjon

Last ned `effektvakt.zip` fra [siste release](https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest) og pakk den ut i `/config/custom_components/effektvakt`. Start Home Assistant på nytt.

Deretter **Settings > Devices & Services > Add Integration > Effektvakt**. Du velger nettselskap, peker på power-sensoren din, og resten har standardverdier som duger. Stegene er beskrevet i [docs/oppsett.md](docs/oppsett.md).

## Dashbord

Integrasjonen har med et eget Lovelace-kort som gjenskaper de gamle analoge effektvaktene som hang i norske sikringsskap. Skiven tegnes fra dine egne kapasitetstrinn, så kronebeløpene på buen er prisene ditt nettselskap faktisk tar.

<p align="center">
  <img src="docs/bilder/dashboard.png" alt="Dashbordet med skive, kort for resten av timen, kutt-kilder og ukesgraf" width="900">
</p>

Rød viser er projisert time-snitt, den tynne svarte er effekten akkurat nå, og trekanten utenfor buen er topp-3-snittet for måneden. Fullførte topper blir stående i månedens tariffgrunnlag.

Kortene ved siden av svarer på det du faktisk lurer på:

<p align="center">
  <img src="docs/bilder/resten-av-timen.png" alt="Kort som viser minutter igjen av timen, hvor mye som kan legges til, og hva kuttes nå" width="520">
</p>

Og ukesgrafen viser de faktiske timesnittene, altså tallene nettselskapet fakturerer etter:

<p align="center">
  <img src="docs/bilder/timesnitt-uke.png" alt="Søylegraf med timesnitt for de siste sju dagene" width="640">
</p>

Se [docs/dashboard-kort.md](docs/dashboard-kort.md) for oppsett, stiler og full forklaring av merkene på skiven. Bildene viser norsk grensesnitt; kortets tekster følger språkvalget i Home Assistant.

## Kvalitet og utvikling

CI kjører samme porter som lokalt:

```bash
just test
just test-ha target=minimum
just test-ha target=current
just coverage
```

`just test` kjører enhetstester, lint, formattering, mypy og vulture. Ekte HA testes både på lovet minimum og aktuell versjon. `just coverage` kombinerer enhetstester og ekte HA-tester og krever minst 95 % samlet linjedekning. Begge dekningsrapportene lastes opp til [Codecov](https://app.codecov.io/gh/fredrik-lindseth/hacs-effektvakt); merket over viser tjenestens tilgjengelige rapport. HACS-validering og hassfest kjøres også i CI. Se [utviklerguiden](docs/development.md) for miljøene og kommandoene.

## Dokumentasjon

| Dokument                                           | Innhold                            |
| -------------------------------------------------- | ---------------------------------- |
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
