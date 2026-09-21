# Oppsett

Effektvakt settes opp fra **Settings > Devices & Services > Add Integration > Effektvakt**. Konfigurasjonsflyten har tre steg, og alt kan endres etterpå under **Configure**.

---

## Steg 1: Nettselskap

Velg nettselskapet ditt fra listen. Effektvakt kjenner kapasitetstrinnene og månedsprisene til 72 norske nettselskap, og henter dem automatisk. Står ikke ditt nettselskap der, eller har du egne trinn du vil regne mot, velger du **Egendefinert** og legger inn tersklene selv.

Hvor dataene kommer fra og hvordan de oppdateres står i [dso.md](dso.md).

---

## Steg 2: Sensorer

| Sensor                | Krav     | Beskrivelse                                             |
| --------------------- | -------- | ------------------------------------------------------- |
| Power-sensor          | Påkrevd  | Instantan effekt (W eller kW), oppdateres hvert 2-10 sek |
| Energy-sensor         | Anbefalt | Kumulativ kWh-måler, `total_increasing`                 |
| VVB-power-sensor      | Valgfri  | Krevd for strategi `vvb_status` og `vvb_pluss_ekstra`   |
| Ekstra power-sensorer | Valgfri  | Krevd for strategi `vvb_pluss_ekstra`                   |

Power-sensoren er den eneste som må være der. Uten energy-sensor estimeres forbruket så langt i timen fra effekt ganger tid, som er dårligere de første minuttene av hver time.

Krav til oppdateringsfrekvens, enheter og hvilke AMS-lesere og smarte plugger som duger, står i [input-sensorer.md](input-sensorer.md).

---

## Steg 3: Innstillinger

| Innstilling           | Standard | Beskrivelse                                                |
| --------------------- | -------- | ---------------------------------------------------------- |
| Sikkerhetsbuffer (kW) | 1,0      | Margin under terskelen som trigger `medium`-risiko         |
| Min risiko for kutt   | medium   | Under dette nivået er `binary_sensor` av                   |
| Risiko-holdetid (min) | 5        | Hvor lenge nedgang i risiko må holde seg før det bekreftes |
| Kutt-strategi         | blind    | Se [strategi.md](strategi.md)                              |

Sikkerhetsbufferen er hovedknappen. En stor buffer gir tidligere varsel og flere kutt, en liten gir færre kutt og mindre margin når du bommer. Holdetiden finnes for at risikoen ikke skal falle tilbake i samme sekund som effekten dipper, så lasten ikke blir slått av og på gjentatte ganger i samme time.

Hvordan risikonivåene regnes ut fra margin og buffer står i [sensorer.md](sensorer.md), og formlene i [beregninger.md](beregninger.md).
