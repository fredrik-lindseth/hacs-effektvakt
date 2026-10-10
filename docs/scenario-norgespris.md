# Uten Norgespris – eller med høyere Norgespris

Ved 16 000 kWh i året betyr 10 øre høyere Norgespris **1 600 kr mer i året**. Uten Norgespris avhenger forskjellen av prisene akkurat når strømmen brukes, etter strømstøtte.

## Samme forbruk, ulike priser

Dette er et syntetisk regneeksempel med spotavtale, 25 % mva og under 5 000 kWh hver måned. Forbruk og klokkeslett er uendret. Nettleie, elavgift, Enovaavgift og leverandørens påslag/fastbeløp er utelatt fra begge alternativer. Tabellen viser kraftkostnaden, ikke hele regningen eller sparing fra Effektvakt.

Norgespris er 50 øre/kWh inkludert mva ut 2026. Uten Norgespris dekker strømstøtten i 2026 90 % av timeprisen over 77 øre uten mva, tilsvarende 96,25 øre med mva. Ordningene kombineres ikke. [NVE om strømstøtte](https://www.nve.no/reguleringsmyndigheten/kunde/stroem/dette-er-stroemstoetteordningen/), [Regjeringen om Norgespris og forbrukstak](https://www.regjeringen.no/no/tema/energi/strom/sporsmal-og-svar-om-norgespris/id3089310/).

Hver rad antar samme spotpris i **alle timer**, ikke et årsgjennomsnitt. Alle priser inkluderer mva. Positiv forskjell betyr at spotalternativet koster mer enn Norgespris på 50 øre.

| Spotpris (øre/kWh) | Etter støtte (øre/kWh) | Kraft per år (kr) | Forskjell fra Norgespris 50 øre (kr/år) |
| ---: | ---: | ---: | ---: |
| 30 | 30 | 4 800 | −3 200 |
| 50 | 50 | 8 000 | 0 |
| 75 | 75 | 12 000 | +4 000 |
| 100 | 96,625 | 15 460 | +7 460 |
| 150 | 101,625 | 16 260 | +8 260 |
| 200 | 106,625 | 17 060 | +9 060 |

For en time med spotpris `P` i øre inkludert mva blir nettoen `P − 0,90 × maks(0, P − 96,25)`. Multipliser med timens kWh og summer. Med halvparten av forbruket til 50 øre og halvparten til 150 øre blir årskostnaden **12 130 kr**, selv om gjennomsnittlig spotpris er 100 øre. Å beregne støtte fra gjennomsnittet ville feilaktig gitt 15 460 kr.

## Hvis Norgespris blir dyrere

| Norgespris med mva | Kraft per år | Mer enn ved 50 øre |
| ---: | ---: | ---: |
| 50 øre/kWh | 8 000 kr | 0 kr |
| 60 øre/kWh | 9 600 kr | 1 600 kr |
| 70 øre/kWh | 11 200 kr | 3 200 kr |

60 og 70 øre er hypotetiske valg, ikke en prognose eller oppgitte 2027-satser. Regjeringen oppgir at prisen skal justeres fra 2027; en sammenligning da må bruke de reglene som faktisk gjelder. [Offisiell prisperiode](https://www.regjeringen.no/no/tema/energi/strom/sporsmal-og-svar-om-norgespris/id3089310/).

## Hva kan Effektvakt påvirke?

Et lavere kapasitetstrinn reduserer nettleien med begge prisordningene. Høyere Norgespris øker verdien av sparte kWh, men ikke kronegevinsten ved et bestemt trinnskifte. Norgespris gjør ikke utsatt oppvarming til spart energi. Innenfor forbrukstaket gir flytting mellom spotpristimer ingen forskjell i selve kraftprisen med Norgespris; nettleien kan fortsatt variere.

Uten Norgespris må eventuell prisstyring bruke prisen etter støtte. Effektvakt har ikke automatisk spotprisplanlegging. Avregning og støtteberegning hører til Strømkalkulator. Se også [sparepotensial og simulering](sparepotensial.md).
