# Oppsett

Effektvakt settes opp fra **Settings > Devices & Services > Add Integration > Effektvakt**. Oppsettet spør bare om nettselskap og sensorer. Alt annet har fornuftige standardverdier og justeres etterpå under **Configure**, når du har sett hvordan det oppfører seg hos deg.

---

## Steg 1: Nettselskap

Velg nettselskapet ditt fra listen. Effektvakt kjenner kapasitetstrinnene og månedsprisene til 72 norske nettselskap, og henter dem automatisk. Står ikke ditt nettselskap der, eller har du egne trinn du vil regne mot, velger du **Egendefinert** og legger inn tersklene selv.

Hvor dataene kommer fra og hvordan de oppdateres står i [dso.md](dso.md).

---

## Steg 2: Sensorer

| Sensor        | Krav     | Beskrivelse                                              |
| ------------- | -------- | -------------------------------------------------------- |
| Power-sensor  | Påkrevd  | Instantan effekt (W eller kW), oppdateres hvert 2-10 sek  |
| Energy-sensor | Anbefalt | Kumulativ kWh-måler, `total_increasing`                  |

Power-sensoren er den eneste som må være der. Uten energy-sensor estimeres forbruket så langt i timen fra effekt ganger tid, som er dårligere de første minuttene av hver time.

Ser sensoren ut som et peak- eller snitt-aggregat, får du en advarsel om det, og da kommer en avkryssingsboks der du kan bekrefte at den likevel rapporterer instant-effekt.

Krav til oppdateringsfrekvens, enheter og hvilke AMS-lesere og smarte plugger som duger, står i [input-sensorer.md](input-sensorer.md).

Etter dette steget er Effektvakt i gang.

---

## Innstillingene: Configure

Under **Settings > Devices & Services > Effektvakt > Configure** ligger resten. Feltene viser alltid det som gjelder nå, så du kan endre én ting uten å røre de andre.

Configure åpner på en meny: **Innstillinger**, **Legg til en kuttbar last**, **Endre eller fjern en kuttbar last** og **Ferdig**. Alt lagres med en gang du svarer, så du kan lukke dialogen når du er ferdig.

Under Innstillinger:

| Innstilling           | Standard             | Beskrivelse                                                |
| --------------------- | -------------------- | ---------------------------------------------------------- |
| Sikkerhetsbuffer (kW) | 1,0                  | Margin under terskelen som gir `like_under_terskel`         |
| Min risiko for kutt   | Like under terskelen | Under dette nivået er `binary_sensor` av                    |
| Risiko-holdetid (min) | 5                    | Hvor lenge nedgang i risiko må holde seg før det bekreftes  |

Sikkerhetsbufferen er hovedknappen. En stor buffer gir tidligere varsel og flere kutt, en liten gir færre kutt og mindre margin når du bommer. Holdetiden finnes for at risikoen ikke skal falle tilbake i samme sekund som effekten dipper, så lasten ikke blir slått av og på gjentatte ganger i samme time.

Standardverdiene duger den første uken. Vent til du har sett noen dager med ekte forbruk før du skrur på dem.

Hvordan risikonivåene regnes ut fra margin og buffer står i [sensorer.md](sensorer.md), og formlene i [beregninger.md](beregninger.md).

---

## Kuttbare laster

En kuttbar last er noe du kan slå av en halvtime uten at noen merker det: en bereder, en varmepumpe, en billader, varmekabler. Hver last er en effektsensor, en valgfri bryter og en terskel for når lasten regnes som på.

Lastene er det `sensor.effektvakt_tilgjengelig_kutt` summerer, og uten dem opprettes ikke den sensoren i det hele tatt. Legger du inn bryteren også, ser Effektvakt når lasten faktisk ble kuttet, og det er grunnlaget for hendelsesloggen.

Legg dem inn under **Configure > Legg til en kuttbar last**. Full forklaring med fornuftige terskler per lasttype står i [laster.md](laster.md).
