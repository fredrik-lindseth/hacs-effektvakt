# Input-sensorer

## TL;DR

| Sensor | Krav | Grunnlag |
| --- | --- | --- |
| Effekt, W/kW | Påkrevd | AMS/HAN eller annen målt øyeblikkseffekt |
| Energi, Wh/kWh | Anbefalt | Kumulativ teller med `total_increasing` |
| Effekt per last | Valgfri | Faktisk forbruk i lasten |
| Aktuator per last | Valgfri | Samme switch eller climate-entitet som styringen bruker |

## Power-sensor (påkrevd)

Velg øyeblikkseffekt i `W` eller `kW`, helst rapportert hvert 2.–10. sekund. Tibber Pulse, Pow-U, ESPHome og HAN/MQTT er mulige kilder. Effekter over 100 kW avvises.

`unknown`, `unavailable`, ugyldige tall/enheter og rapporter eldre enn 120 sekunder gir ukjent beregning. Friskhet måles fra `last_reported`, ellers `last_updated`; en uendret verdi kan fortsatt være fersk. Attributtene `maalegrunnlag_gyldig`, `beregning_gyldig` og `maalegrunnlag_problem` forklarer tilstanden. Målefeil opphever aldri ansvaret for å gjeninnkoble overtatte laster.

### Unngå peak-sensorer

Maks- og snittsensorer er ikke øyeblikkseffekt. Oppsettet advarer ved navn med peak/max/average-mønstre og krever bekreftelse dersom du bruker sensoren likevel.

## Energy-sensor (anbefalt)

Velg en kumulativ `Wh`- eller `kWh`-teller med `state_class: total_increasing`, for eksempel målerens importenergi (OBIS 1.8.0). Den skal stige med forbruket.

### Hvorfor energy-sensor gir bedre projeksjon

Effekt integreres mellom avlesningene; energimåleren korrigerer anslaget uten dobbelttelling. Den kan også fylle målehull og rette forrige time etter timeskiftet. Se [timeregnskapet](beregninger.md#actual_kwh_this_hour).

## Sensorer for kuttbare laster (valgfrie)

Bruk én effektsensor per fysisk last. Tilgjengelig kutt summerer målte laster over deres egen terskel. Aktuatoren knytter lasten til styringen og lastvernets eierskap; `heat`-modus er ikke en wattmåling. Terskler og eksempler står i [laster.md](laster.md).

En manuell [lastprofil](lastprofiler.md) kan brukes uten effektsensor til planlegging. Den gir ikke kapasitet til automatisk kuttvurdering uten aktuell måling.

## Validering ved oppsett

Oppsettet kontrollerer at sensoren finnes, har godkjent enhet og viser et endelig tall. Ugyldig sensor blokkerer lagring; et peak/max/average-navn gir advarsel.
