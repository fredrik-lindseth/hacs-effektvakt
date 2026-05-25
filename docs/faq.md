# Ofte stilte spørsmål

## Er det trygt å skru varmtvannstanken av og på automatisk?

Ja, for av-perioder på 15-60 minutter. En 200-liters bereder mister typisk 0,5-2 °C per time ved god isolasjon. Et halvtimes av-vindu kjøler vannet noen få grader, det merkes ikke. Termostaten din skrur elementet av og på flere ganger i timen uansett, Effektvakt legger bare på en ekstra syklus.

## Får jeg legionella av dette?

Nei. Legionella er en bakterie som trenger 25-50 °C og tid for å vokse. Over 55 °C er det ingen vekst. Over 60 °C dør den aktivt. En riktig innstilt bereder står på 65-75 °C i drift.

Regn på det: hvis tanken står på 70 °C og mister 2 °C/time, er den fortsatt 68 °C etter en time. Det er langt over risiko-sonen. For å nå 50 °C måtte du la den stå av i ti timer. Effektvakt slår av i maks 30 minutter (failsafe) før den uansett tvinges på igjen.

Praktiske tommelfingerregler:

- Hold termostaten på minst 65 °C i drift
- Ikke la tanken stå av i mer enn 4-6 timer kontinuerlig (varmetap, ikke bakteriefare)
- Spyl gjennom lite brukte tappesteder (gjesteservant) noen ganger i året

## Sliter elementet av at det slås av og på?

Marginalt, ikke nok til å bekymre seg over. Termostaten din skrur elementet av og på naturlig hver gang vannet svinger noen grader rundt setpunktet, ofte 10-20 ganger per dag. En ekstra automatisk syklus per time fra Effektvakt er ikke merkbar tilleggsbelastning.

Det som SLITER elementer er hyppige raske av/på under last (sekund-skala, ikke minutt-skala) og dårlig vannkvalitet (kalk og sediment). Ingen av delene relevant for Effektvakt.

## Sløser jeg strøm på å varme opp igjen?

Nei, det er en vanlig misforståelse. Termodynamisk: hvis tanken slipper ut X kWh varme mens den er av, så bruker den nøyaktig X kWh på å varme det opp igjen. Det er ingen straffekostnad.

Faktisk: hvis tanken får stå litt kaldere mens den er av, blir varmetapet litt lavere fordi temperaturforskjellen mot rommet er mindre. Effekten er liten (1-2%), men retningen er at av/på-styring er **marginalt mer effektivt** enn å la tanken stå konstant på.

## Hvor lenge kan tanken stå av før jeg merker det?

For en 200-liters bereder med termostatinnstilling 70 °C: 4-6 timer ved typisk bruk, før vannet du tapper blir merkbart kjøligere. Effektvakt sine standard 15-30 minutters kuttvinduer er usynlig for brukeren.

Hvis du dusjer rett etter et lastkutt, vil du ikke merke noe så lenge tanken var varm før kuttet begynte.

## Hvor mye sparer jeg egentlig på dette?

Det avhenger sterkt av hvor du ligger i kapasitetstrinnene. Nettleien faktureres etter snittet av topp-3 maks-timer fra ulike dager i måneden. For BKK koster det typisk:

| Trinn    | Pris per måned |
| -------- | -------------- |
| 2-5 kW   | ca. 230 kr     |
| 5-10 kW  | ca. 415 kr     |
| 10-15 kW | ca. 600 kr     |
| 15-20 kW | ca. 800 kr     |

Hvis Effektvakt hindrer at du krysser fra et trinn til neste, sparer du 100-300 kr per måned så lenge du holder deg under. Hvis du allerede ligger godt midt i et trinn (f.eks. topp-3-snitt på 7 kW i 5-10 kW-trinnet), gir kutting null besparelse den måneden.

Effektvakt har størst verdi i månedene der du ligger like under en trinngrense.

## Hvor mye effekt får jeg faktisk kuttet ved å slå av VVB?

Mindre enn folk tror, hvis du ikke har en VVB-effekt-sensor.

Norsk standard VVB (OSO Saga f.eks.) har 2 kW element. MEN: tanken bruker bare 10-15% av tiden på aktiv oppvarming i normal drift. Resten av tiden ligger elementet i pause mens vannet holder temperatur.

Hvis Effektvakt blindt slår av VVB i et tilfeldig 30-min-vindu, er det 85-90 % sjanse for at elementet uansett var av på det tidspunktet. Forventet effekt-kutt: 0,1-0,2 kWh.

For å garantere kutt trenger du en sensor som rapporterer VVB-effekten i sanntid. Da kan Effektvakt slå av kun når elementet faktisk varmer. Det gir ca. 1 kWh kutt per 30-min event.

Dette er hvorfor v0.2 av Effektvakt vil støtte en valgfri `vvb_power_sensor`-konfig.

## Hva med elbil-lader?

Hjemmeladere på 3,6-22 kW er den eneste enkeltkilden som gir umiddelbar stor effektreduksjon ved pause. 30 minutter pause = 1,8-11 kWh kutt, og bilen merker det knapt (laden tar bare litt lenger tid).

Hvis du har elbil er det den klart viktigste lasten å koble på Effektvakt-styring.

## Hvilke laster bør jeg kutte, i prioritert rekkefølge?

1. **Elbil-lader** (3,6-22 kW). Ingen komfortkostnad, kjempestor fleksibilitet.
2. **Varmtvannsbereder** (1,5-3 kW, 0 komfortkostnad under 60 min).
3. **Panelovner** (0,5-2 kW per ovn, treghet i romtemperatur gir 15-30 min buffer).
4. **Gulvvarme** (1-3 kW, lang treghet).

Unngå å kutte induksjonstopp (irriterende mid-matlaging) og tørketrommel/vaskemaskin/oppvaskmaskin (programmene tåler dårlig avbrudd).

## Konkrete tall fra en norsk husholdning

Faktisk effektmåling fra et hus i Bergen (4-5 m² baderom, gulvvarme på 130 W/m²):

| Sone                              | Max effekt       | Snitt over tid |
| --------------------------------- | ---------------- | -------------- |
| Bad gulvvarme                     | 557 W            | 183 W          |
| Stue gulvvarme                    | ca. 1100 W       | n/a            |
| Kjøkken gulvvarme                 | typisk 500-800 W | n/a            |
| Gang gulvvarme                    | typisk 400-700 W | n/a            |
| **Sum gulvvarme**                 | **~3 000 W**     | varierer       |
| Varmtvannsbereder (OSO Saga 200L) | 2 000 W          | ~250 W         |
| Panelovn typisk                   | 600-1500 W       | 200-600 W      |

For en husholdning som vanligvis ligger like under et kapasitetstrinn, kan kombinasjonen "VVB + 2-3 varmekabler + 1 panelovn" gi 3-5 kW tilgjengelig kutting, mer enn nok til å hindre en trinn-overskridelse på 10 kW eller 15 kW.

## Kilder

Legionella-biologi:

- [PMC - Water Heater Type, Temperature Setting, and Legionella Growth (2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11731276/): vekstrater per temperatur, eksperimentelle tall
- [Heat Geek - Legionella and Water Temperature](https://www.heatgeek.com/articles/legionella-and-water-temperature-what-you-need-to-know): praktisk forklaring av temperatur-tid-forholdet
- [Energy Vanguard - Water Heater Cycling and Legionnaires Disease](https://www.energyvanguard.com/blog/will-your-water-heater-give-you-legionnaires-disease/): cycling-spesifikk diskusjon

VVB-effekt og duty cycle:

- [OSO Hotwater - Saga Standard](https://osohotwater.no/product/varmtvannsbereder-saga-standard/): typisk norsk standard-bereder
- [Energy Vanguard - 3 Types of Energy Efficiency Losses in Water Heating](https://www.energyvanguard.com/blog/the-3-types-of-energy-efficiency-losses-in-water-heating/)
- [ByggeBolig - Tidsstyring på varmtvannsbereder](https://byggebolig.no/el-varmtvannsbereder/tidsstyring-pa-varmtvannsbereder): norske brukererfaringer

Norsk kontekst:

- [Tu.no - Hvordan styre effektforbruket](https://www.tu.no/artikler/ny-nettleie-hvordan-styre-effektforbruket/515299)
