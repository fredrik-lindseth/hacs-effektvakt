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

Bare kutt som flytter månedens fakturerte kapasitetstrinn reduserer kapasitetsleddet. [BKK-eksemplet](sparepotensial.md#regnestykket-fra-bkk) gir 330 kr i mulig reduksjon over to måneder ved 1 kW lavere topp-3-snitt. Det er beregnet potensial, ikke målt sparing.

## Hvor mye effekt får jeg faktisk kuttet ved å slå av VVB?

Når elementet varmer, viser effektsensoren det momentane bidraget. Energi som kan flyttes avhenger av hvor lenge elementet ellers ville gått. Legg inn [lasten](laster.md), og bruk en [profil](lastprofiler.md) for varighetsanslaget.

## Hva med elbil-lader?

Lading kan gi stort bidrag når den pågår. Bruk laderens støttede styring og behold nok ladetid før bilen skal brukes.

## Hvilke laster bør jeg kutte, i prioritert rekkefølge?

Velg en aktiv last som forventes å dekke energibehovet med minst ulempe. Lading, varmtvann og treg romoppvarming kan passe, avhengig av frister og temperatur. Ikke avbryt apparatprogrammer uten at apparatet støtter det.

## Hvordan finne ut hva ditt eget hus drar

Bruk typeskilt eller installasjonsdokumentasjon for nominell effekt og wattmålinger for faktisk drift. Termostatmodus viser ikke at elementet varmer. [Lastprofilverktøyet](lastprofiler.md#eksporter-historikken-fra-home-assistant) kan analysere din egen historikk.

## Kilder

Tariffgrunnlaget står i [dso.md](dso.md), beregningene i [beregninger.md](beregninger.md) og styringsgrensene i [blueprints.md](blueprints.md). Apparatsikkerhet og temperaturkrav må komme fra produsentens dokumentasjon.
