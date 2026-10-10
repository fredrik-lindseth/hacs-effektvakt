# Eksempelrapport for en lastprofil

[English](lastprofil-rapport.en.md)

Denne rapporten bruker kunstige data fra [metodikkens eksempelfil](../lastprofiler.md#kjør-analysen-selv). Den viser hvordan du kan dokumentere en analyse av eget anlegg uten å publisere råhistorikk. Tallene beskriver ingen bestemt husholdning.

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

Oppgi målevindu, tidssone, terskel, kjent dekning og om verdier ble holdt videre. Skill målte tall fra manuell nominell effekt og antatt arbeidssyklus. Noter antall hele sykluser som støtter restvarighetsanslaget. Sammenlign med faktiske topptimer framfor å bruke døgnsnitt alene.

Har flere sensorer samme fysiske last, kontroller enheter, brytertilstand og ferskhet før du summerer. En kontrollert på/av-observasjon kan avdekke kanaler som holder en gammel effekt eller rapporterer null. Høy tilstandsdekning alene bekrefter ikke riktige målinger. Rapporter uavklarte kanaler som uavklart grunnlag.

En rapport om sparing bør vise utkobling og gjeninnkobling, og hvor utsatt energi ble av. [BKK-regneeksemplet og simuleringen](../sparepotensial.md#regneeksempel-og-simulert-styring) sammenligner ideelle reduksjoner med en modell som fører energien tilbake. Det er ikke nok å multiplisere dagens aktiveffekt med resten av timen og kalle resultatet spart nettleie.

Personlig råhistorikk og faktiske husholdningsprofiler kan oppbevares lokalt. Velg bevisst hva du vil dele i en offentlig rapport.
