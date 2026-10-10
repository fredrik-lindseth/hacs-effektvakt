# Ofte stilte spørsmål

## Er det trygt å skru varmtvannstanken av og på automatisk?

Bruk koblingsutstyr og tidsgrenser som passer berederen. [Lastvernet](blueprints.md#gjeninnkoblingsvern) håndhever gjeninnkobling og minste påtid, men måler ikke vanntemperatur eller varmtvannsbehov.

## Får jeg legionella av dette?

Effektvakt gir ingen hygienegaranti. Behold produsentens temperaturinnstillinger og hygienefunksjoner; ikke senk dem på grunnlag av et lastkutt.

## Sliter elementet av at det slås av og på?

Følg apparatets koblingsgrenser. Minste påtid og hysterese begrenser rask kobling; integrasjonen kjenner ikke komponentenes levetid.

## Sløser jeg strøm på å varme opp igjen?

Utsatt varme må vanligvis tas igjen og kan lage en ny topp. Lavere kapasitetstrinn kan spare kroner uten å spare kWh. Se [simuleringen](sparepotensial.md#regneeksempel-og-simulert-styring).

## Hvor lenge kan tanken stå av før jeg merker det?

Velg grensen etter tank, temperatur og tapping. Timeskiftet er en styringsfrist, ikke et løfte om nok varmtvann.

## Hvor mye sparer jeg egentlig på dette?

BKKs trinnskifte fra 5–10 til 2–5 kW sparer 165 kr/måned: to, fire eller fem slike måneder gir 330, 660 eller 825 kr/år. Bare faktisk lavere fakturert trinn sparer kapasitetsledd. [Årsregnestykke](sparepotensial.md#hva-kan-det-bli-på-et-år).

Trinngrense, samtidighet, kulde, elbil, oppvarming og komfort avgjør muligheten. Høyt årsforbruk alene betyr ikke stor kapasitetssparing. Norgespris endrer ikke gevinsten ved et bestemt trinnskifte.

## Hvor mye effekt får jeg faktisk kuttet ved å slå av VVB?

Effektsensoren viser bidraget når elementet varmer. [Lastprofilen](lastprofiler.md) anslår hvor lenge det ellers ville fortsatt.

## Hva med elbil-lader?

7,4 kW i en halvtime bidrar med 3,7 kWh til timen. Flytt lading til timer med plass, og behold nok ladetid. Bruk laderens støttede styring; Effektvakt har ingen egen ladeplanlegger.

3 000 kWh flyttet helt fra BKKs dagtariff til natt/helg gir omtrent 685 kr/år i energiledd med 2026-satser. Allerede flyttet lading gir ingen ny gevinst; kapasitet vurderes separat. [Tidsflytting](scenario-nattvask.md).

## Påvirker solceller dette?

Ja: 6 kW forbruk minus 2 kW samtidig produksjon gir 4 kW nettuttak. Kapasitetstrinnet reduseres bare når produksjonen hjelper i de avgjørende topptimene; sommersol hjelper ikke mot vintertopper etter solnedgang.

Mål [nettuttak](input-sensorer.md#solceller), uten å trekke produksjonen fra to ganger. Forbruk i soltimer må sammenlignes med eksportinntekten du gir avkall på. [NVE om egenforbruk](https://www.nve.no/reguleringsmyndigheten/kunde/stroemnettet/prosumenter-og-plusskunder/).

## Hvilke laster bør jeg kutte, i prioritert rekkefølge?

Velg aktive laster som dekker behovet med minst ulempe og innen temperatur/frister. Ikke avbryt apparatprogrammer uten støtte for det.

## Hvordan finne ut hva ditt eget hus drar

Typeskilt viser nominell effekt, wattmåling faktisk drift. Termostatmodus er ikke målt aktivitet. [Analyser egen historikk](lastprofiler.md#eksporter-historikken-fra-home-assistant).
