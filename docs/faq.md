# Ofte stilte spørsmål

## Er det trygt å skru varmtvannstanken av og på automatisk?

Bruk tidsgrenser og koblingsutstyr som passer berederen. Lastvernet slipper ved timeskiftet eller maksimal utkobling, og håndhever minste påtid. Det kontrollerer ikke vanntemperatur eller varmtvannsbehov. Se [gjeninnkoblingsvernet](blueprints.md#gjeninnkoblingsvern).

## Får jeg legionella av dette?

Effektvakt måler ikke vanntemperatur og gir ingen hygienegaranti. Behold produsentens temperaturinnstillinger og eventuelle hygienefunksjoner; ikke bruk et lastkutt som grunnlag for å senke dem.

## Sliter elementet av at det slås av og på?

Velg et relé som tåler lasten og følg apparatets grenser. Minste påtid og hysterese begrenser rask gjentatt kobling, men integrasjonen kjenner ikke komponentenes levetid.

## Sløser jeg strøm på å varme opp igjen?

Utsatt oppvarming må vanligvis tas igjen. Et lavere kapasitetstrinn kan spare kroner uten å spare kWh, og gjenoppvarming kan lage en ny topp. [Simuleringen](sparepotensial.md#regneeksempel-og-simulert-styring) viser dette.

## Hvor lenge kan tanken stå av før jeg merker det?

Det avhenger av tank, temperatur og tapping. Velg maksimal utkobling etter ditt behov; et timeskifte er en styringsfrist, ikke et løfte om nok varmt vann.

## Hvor mye sparer jeg egentlig på dette?

Hos BKK gir et trinnskifte fra 5–10 til 2–5 kW 165 kr mindre nettleie per måned. Lykkes du i to, fire eller fem måneder, blir det 330, 660 eller 825 kr/år. Du sparer kapasitetsledd bare når månedens fakturerte trinn faktisk blir lavere. Se [årsregnestykket og forutsetningene](sparepotensial.md#hva-kan-det-bli-på-et-år).

Det avgjørende er hvor nær trinngrensen du ligger, og om du kan flytte forbruk fra topptimene uten å lage nye topper. Elbil, elektrisk oppvarming, bereder, kulde og komfortkrav påvirker dette. Et hus som allerede ligger trygt i sitt billigste aktuelle trinn, kan få null gevinst i kapasitetsleddet selv med høyt årsforbruk. Norgespris endrer kraftprisen, ikke besparelsen ved et bestemt kapasitetstrinn.

## Hvor mye effekt får jeg faktisk kuttet ved å slå av VVB?

Når elementet varmer, viser effektsensoren det momentane bidraget. Energi som kan flyttes avhenger av hvor lenge elementet ellers ville gått. Legg inn [lasten](laster.md), og bruk en [profil](lastprofiler.md) for varighetsanslaget.

## Hva med elbil-lader?

En lader på 7,4 kW som går i en halvtime, bidrar med 3,7 kWh til den timen. Å flytte ladingen kan derfor bety mer for toppene enn å slå av små laster, men den nye timen må ha plass og bilen må bli klar i tide. Bruk laderens støttede styring; Effektvakt har ikke en egen ladeplanlegger.

Som et separat regneeksempel gir 3 000 kWh lading flyttet helt fra BKKs dagtariff til natt/helg omtrent 685 kr/år i lavere energiledd, med 2026-satsene. Dette krever at energien faktisk lå i dagtariffen før; eksisterende nattlading gir ikke samme nye gevinst. Kapasitetstrinnet må vurderes i tillegg. Se [tariffene og tidsflytting](scenario-nattvask.md).

## Påvirker solceller dette?

Ja. Egenproduksjon brukt i huset reduserer kjøpet fra nettet. Med 6 kW forbruk og 2 kW solproduksjon blir nettuttaket 4 kW mens begge holder seg på disse nivåene. For kapasitetstrinnet teller timegjennomsnittet og månedens tre høyeste dager: solcellene må produsere i de relevante timene for å senke trinnet. Sommertilgang hjelper ikke mot en vintertopp etter solnedgang.

Effektvakt trenger måling av uttak fra nettet, ikke husets bruttoforbruk. Ikke trekk produksjonen fra en gang til hvis måleren allerede viser nettuttaket; se [sensorkravene](input-sensorer.md). Når du flytter forbruk til soltimer, må spart kjøp også sammenlignes med verdien av eksporten du går glipp av. Natt er derfor ikke alltid billigst for en plusskunde. [NVE om egenforbruk og plusskunder](https://www.nve.no/reguleringsmyndigheten/kunde/stroemnettet/prosumenter-og-plusskunder/).

## Hvilke laster bør jeg kutte, i prioritert rekkefølge?

Velg en aktiv last som forventes å dekke energibehovet med minst ulempe. Lading, varmtvann og treg romoppvarming kan passe, avhengig av frister og temperatur. Ikke avbryt apparatprogrammer uten at apparatet støtter det.

## Hvordan finne ut hva ditt eget hus drar

Bruk typeskilt eller installasjonsdokumentasjon for nominell effekt og wattmålinger for faktisk drift. Termostatmodus viser ikke at elementet varmer. [Lastprofilverktøyet](lastprofiler.md#eksporter-historikken-fra-home-assistant) kan analysere din egen historikk.

## Kilder

Tariffgrunnlaget står i [dso.md](dso.md), beregningene i [beregninger.md](beregninger.md) og styringsgrensene i [blueprints.md](blueprints.md). Apparatsikkerhet og temperaturkrav må komme fra produsentens dokumentasjon.
