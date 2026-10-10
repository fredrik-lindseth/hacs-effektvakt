# Eksempelrapport for en lastprofil

Kunstig eksempel fra [metodikkens eksempelfil](../lastprofiler.md#kjør-analysen-selv), med tabell og forutsetninger du kan bruke i egen rapport.

## Målevindu og grunnlag

Vinduet er 1. januar 2026 klokken 00:00–01:00 i norsk vintertid. Lasten trekker 0 W de første ti minuttene, 300 W de neste tjue minuttene og 0 W de siste tretti minuttene. Terskelen er 100 W. Tilstander holdes fram til neste registrerte endring; det er ingen ukjente intervaller innenfor vinduet.

| Resultat | Verdi |
| --- | ---: |
| Kjent tid | 60 minutter |
| Aktiv tid | 20 minutter |
| Tilstandsdekning | 100 % |
| Arbeidssyklus | 33,3 % |
| Effekt når aktiv | 300 W |
| Tidsvektet middel | 100 W |
| Energi | 0,100 kWh |
| Hele påperioder | 1 |

Etter ti minutters påtid har den eneste sammenlignbare syklusen ti minutter igjen. Restvarighetsanslaget har ett støttende tilfelle. Å velge tjue minutters forventet videre drift ville gå ut over det eksemplet støtter.

## Bruk tallene

Hvis lasten ellers ville gått ti minutter til, bidrar et kutt med 300 W × 10/60 time = 0,050 kWh. Det reduserer timegjennomsnittet med 50 W. Den momentane effekten er 300 W, men profilen beskriver et mindre bidrag over klokketimen.

Som et separat manuelt scenario gir 2 000 W samlet gulvvarme pluss 300 W i en annen sone, med antatt 15 % arbeidssyklus, 345 W i gjennomsnitt. Dette er en antakelse, og sier ikke hvilke soner som faktisk varmer samtidig. Tell hver sone én gang og vurder bad eller andre laster separat.

## Slik dokumenterer du ditt eget anlegg

Oppgi målevindu, tidssone, terskel, dekning, viderehold av verdier og antall hele støttende sykluser. Skill måling fra nominell effekt og antatt arbeidssyklus. Sammenlign med topptimene, ikke bare døgnsnitt.

Kontroller enhet, ferskhet og aktuator før summering; ikke tell samme last flere ganger. Uavklarte sensorkanaler gir uavklart grunnlag.

Dokumenter kutt, gjeninnkobling og hvor utsatt energi havnet før du kaller det spart nettleie. [Simuleringen](../sparepotensial.md#regneeksempel-og-simulert-styring) viser forskjellen. Hold personlig råhistorikk lokalt.
