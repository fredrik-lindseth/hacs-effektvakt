# Oppsett

Effektvakt settes opp fra **Settings > Devices & Services > Add Integration > Effektvakt**. Oppsettet spør bare om nettselskap og sensorer. Alt annet har fornuftige standardverdier og justeres etterpå under **Configure**, når du har sett hvordan det oppfører seg hos deg.

---

## Steg 1: Nettselskap

Velg nettselskapet ditt fra listen. Kildetabellen inneholder 71 nettselskap; de 69 med støttet topp-3-metode kan velges. Sør Aurdal Energi og Tinfos er sperret fordi de bruker henholdsvis månedsmaks og uverifisert metode. Står ikke ditt nettselskap der, eller har du egne trinn du vil regne mot, velger du **Egendefinert** og legger inn tersklene selv.

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

Configure åpner på en meny med innstillinger, kuttbare laster og Ferdig. Utviklingsversjonen har også Mål for måneden. Alt lagres med en gang du svarer, så du kan lukke dialogen når du er ferdig.

Under Innstillinger:

| Innstilling           | Standard             | Beskrivelse                                                |
| --------------------- | -------------------- | ---------------------------------------------------------- |
| Sikkerhetsbuffer (kW) | 1,0                  | Margin som bestemmer når forvarselet begynner         |
| Min risiko for kutt   | Like under terskelen | Under dette nivået er `binary_sensor` av                    |
| Risiko-holdetid (min) | 5                    | Hvor lenge nedgang i risiko må holde seg før det bekreftes  |

En stor sikkerhetsbuffer gir tidligere forvarsel. De høyeste risikonivåene krever i tillegg at kuttkriteriet viser en unngåelig kostnad; buffer alene utløser dem ikke. Holdetiden finnes for at risikoen ikke skal falle tilbake i samme sekund som effekten dipper, så lasten ikke blir slått av og på gjentatte ganger i samme time.

Standardverdiene duger den første uken. Vent til du har sett noen dager med ekte forbruk før du skrur på dem.

Hvordan risikonivåene regnes ut fra margin og buffer står i [sensorer.md](sensorer.md), og formlene i [beregninger.md](beregninger.md).

---

## Kuttbare laster

Registrer laster du kan utsette innenfor deres behov og tidsgrenser. Effektsensoren beskriver aktivitet; aktuatoren knytter lasten til styringen. Lastvernet eier gjeninnkobling av overtakelser gjennom `effektvakt.styr_last`.

Legg dem inn under **Configure > Legg til en kuttbar last**. Full forklaring med fornuftige terskler per lasttype står i [laster.md](laster.md).

## Mål for måneden

Utviklingsversjonen har et valgfritt **Mål for måneden** i konfigurasjonsmenyen. Velg en terskel fra nettselskapets kapasitetstrinn eller **Av** for vanlig vurdering. Et valgt mål kan gi flere og tidligere kutt for å holde plass til senere dager. Allerede registrerte topper avgjør om målet fortsatt kan nås. Les [forutsetningene og avveiningene](sparepotensial.md#et-mål-for-måneden) før du bruker det til automatisk lastkutt.

## Lastprofil per last

Under oppretting eller redigering av en last kan du i utviklingsversjonen velge profil: Av, Historikk (siste sju dager) eller Manuell. Automatisk bruker effektsensorens recorder-historikk. Manuell krever navn, nominell effekt og arbeidssyklus og kan brukes uten effektsensor. Typisk påtid er valgfri. Sett maksimal kuttvarighet etter lasten og samme grense som i blueprinten. [Lastprofiler](lastprofiler.md) forklarer beregningen og forskjellen mellom planleggingsanslag og målt tilgjengelig kutt.

Under Innstillinger er **Bruk lastprofiler i kuttvurderingen** av som standard. Aktiver det for å vurdere energibidraget fra målte aktive laster med profil. Manuelle profiler uten wattmåling gir bare planleggingsanslag. [Virkning og avgrensning](lastprofiler.md#profiler-inne-i-home-assistant).
