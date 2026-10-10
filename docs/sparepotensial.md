# Sparepotensial og lastprofiler

[English](sparepotensial.en.md)

## Regnestykket fra BKK

Månedens historiske topp-3-snitt var 5,823 kW i desember 2025 og 5,702 kW i februar 2026. Med 415 kr per måned over 5 kW og 250 kr på eller under 5 kW gir 1 kW reduksjon snittene 4,823 og 4,702 kW og 165 kr spart i hver måned: til sammen 330 kr. 600 W reduksjon gir 5,223 og 5,102 kW, fortsatt i samme trinn. Timesdataene er beskrevet i [fixtur-dokumentasjonen](../tests/fixtures/README.md).

## Et mål for måneden

I utviklingsversjonen kan du velge **Mål for måneden** under **Konfigurer**. Velg et kapasitetstrinn fra nettselskapets tabell, for eksempel 5 kW. Effektvakt forsvarer da dette målet fra starten av måneden. Det kan gi tidligere og flere kutt enn standardinnstillingen, også når timen ennå ikke kan låse inn dyrere nettleie. Det krever at du vil utsette forbruk for å holde plass til resten av måneden.

Målet endrer ikke regnestykket for fakturert nettleie. Bare dagsmaks som allerede er registrert avgjør om målet fortsatt kan nås. Har tre låste dagsmaks et snitt over målet, får det status `tapt`, og Effektvakt går tilbake til vanlig vurdering av hvilket trinn som fortsatt kan unngås. Målet beholdes i oppsettet og blir prøvd igjen neste måned. Velger du **Av**, brukes standardvurderingen hele tiden.

`maal_kutt_anbefalt` sier at et kutt kan begrense en ny dagsmaks over måltaket. Det lover verken at hele timen kan reddes eller at du sparer et bestemt kronebeløp. `timen_flytter_trinnet` og kostnadsattributtene beskriver fortsatt virkningen på kapasitetstrinnet nå. Les [sensorene](sensorer.md) og behold grensene for maksimal utkobling og minste påtid i [blueprintene](blueprints.md).

## Hva et lastkutt kan bidra med

En last på 600 W som ellers ville gått hele timen, bidrar med 0,6 kWh. Er den bare på i ti minutter, bidrar den med 0,1 kWh. Det er forskjellen i energien over hele klokketimen som avgjør hvor mye timegjennomsnittet kan reduseres. Effekten akkurat nå er derfor ikke nok til å anslå nytten.

`scripts/analyser_lastprofil.py` analyserer tidsstemplede wattmålinger fra en lokal JSON-fil. Det viser tidsvektet påandel, effekt når lasten er på, energi, dekning og varigheten til observerte sykluser. Det kan også begrenses til utvalgte toppvinduer. En last som bruker 500 W og er på en fjerdedel av tiden, har 125 W i tidsvektet gjennomsnitt; det er ikke et løfte om 125 W kutt i neste topptime.

Restvarighet beregnes fra hele observerte sykluser som har vart minst like lenge som den aktuelle påperioden. Rapporten viser hvor mange slike sykluser anslaget bygger på. Perioder som treffer starten eller slutten av målevinduet, eller avbrytes av hull, er ufullstendige og holdes utenfor dette anslaget. Ufullstendige perioder kan likevel gi skjevhet mot korte sykluser. Ukjent effekt regnes ikke som null. Tilstander holdes fram til neste rapport med mindre du velger en maksimal holdetid; høy dekning betyr derfor ikke at sensoren rapporterer ferske eller korrekte verdier.

Termostatmodus `heat` betyr ikke at varmen faktisk trekker strøm. Uten wattmåling kan verktøyet ikke finne påandelen. Flere sensorer for samme last må avklares før de summeres, særlig når de rapporterer forskjellige tall. Lys kan gi et lite bidrag nær en grense; gulvvarme og varmtvann må vurderes sammen med temperatur, behov og hvor mye oppvarming som kommer tilbake senere. Det lokale analyseverktøyet kobler ikke ut laster. Utviklingsversjonen kan bruke profiler fra målte aktive laster i kuttvurderingen når du slår på det valgfrie profilvalget; se [lastprofiler i Home Assistant](lastprofiler.md#profiler-inne-i-home-assistant).

## Regneeksempel og simulert styring

[README-eksemplet](../README.md#et-regneeksempel-fra-bkk) viser 330 kr i mulig reduksjon av kapasitetsleddet dersom topp-3-snittene i desember 2025 og februar 2026 faktisk hadde blitt redusert med 1 kW. Det er et regneeksempel med ideelle kutt gjennom hele de relevante timene.

`scripts/simuler_sparing.py` prøver i stedet å styre underveis i de historiske timene, uten å kjenne framtidige topper. Den bruker timesforbruk som jevn effekt innen hver time, og lar en tenkt fleksibel last være tilgjengelig innenfor husets forbruk. Utsatt energi føres tilbake med valgt effekt, maksimal utkobling og minste påtid. Det er en forenklet modell av flytting av forbruk, ikke en temperaturmodell eller måling av faktisk sparing.

Med 600 W og 1 kW, både vanlig vurdering og et valgt mål på 5 kW, ga denne modellen ingen reduksjon i kapasitetsleddet over de komplette månedene i datagrunnlaget når utsatt energi ble ført tilbake straks med samme effekt. I noen måneder økte topp-3-snittet uten å endre trinnet. Januar 2026 har 105 manglende timer og holdes utenfor samlet sammenligning. Resultatet viser hvorfor gjeninnkoblingen og plasseringen av forbruket senere er like viktig som selve kuttet. Det fastslår ikke at reell styring er uten nytte.

Kjør analysene fra repo-roten:

```bash
uv run --group unit python scripts/simuler_sparing.py
uv run --group unit python scripts/analyser_lastprofil.py profil.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --terskel-w 100
```

Lastprofilens inputformat står i scriptets hjelpetekst. Bruk lokale filer for egen målehistorikk. For å dokumentere reell besparelse trenger vi målinger av tilgjengelige laster i topptimene, faktisk utkobling, gjeninnkobling og forbruk etterpå. Vi viser ikke simulert sparepotensial som en målt besparelse.

Se [metodikken for lastprofiler](lastprofiler.md) og [eksempelrapporten](research/lastprofil-rapport.md) for observasjoner og manuelle antakelser.
