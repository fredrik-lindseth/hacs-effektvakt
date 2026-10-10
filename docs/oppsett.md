# Oppsett

Åpne **Settings → Devices & Services → Add Integration → Effektvakt**. Installasjonen står i [README](../README.md#installasjon).

## Steg 1: Nettselskap

Velg nettselskap eller **Egendefinert** for egne kapasitetstrinn. Kildetabellen har 71 nettselskap; 69 bruker støttet topp-3-metode. Sør Aurdal Energi og Tinfos er sperret på grunn av annen eller ukjent metode. Se [tariffgrunnlaget](dso.md).

## Steg 2: Sensorer

| Sensor | Krav |
| --- | --- |
| Effekt | Påkrevd: målt øyeblikkseffekt i W eller kW. |
| Energi | Anbefalt: kumulativ Wh/kWh-teller med `total_increasing`. |

Uten energimåler beregnes timens forbruk fra effektintegrasjon. Peak- og snittnavn gir advarsel og krever bekreftelse. Enheter, ferskhet og solcelleoppsett står i [sensorkravene](input-sensorer.md).

## Innstillingene: Configure

Under **Konfigurer** kan du endre innstillinger og legge til, redigere eller fjerne laster. Endringer lagres med en gang.

| Innstilling | Standard | Virkning |
| --- | --- | --- |
| Sikkerhetsbuffer | 1 kW | Tidspunkt for forvarsel. |
| Min risiko for kutt | Like under terskelen | Laveste nivå som gir kuttanbefaling. |
| Risiko-holdetid | 5 minutter | Ventetid per trinn ned i risiko. Oppgang er umiddelbar. |

Buffer alene gir ikke høy risiko: [kuttkriteriet](beregninger.md#kuttkriteriet-flytter-denne-timen-trinnet) må også være oppfylt. Begynn med standardverdiene og observer noen dager før du endrer dem.

## Kuttbare laster

Registrer effektmåling, terskel og eventuell aktuator under **Legg til en kuttbar last**. Registreringen beskriver lasten; automatisk kutt krever en [blueprint-automasjon](blueprints.md). Se [lastoppsett](laster.md).

## Mål for måneden

Utviklingsversjonen har et valgfritt månedsmål: velg kapasitetsterskel eller **Av**. Et mål kan gi tidligere og flere kutt, men overtas av vanlig vurdering hvis registrerte topper gjør det umulig. Valget beholdes til neste måned. Se [månedsmålet](sparepotensial.md#et-mål-for-måneden).

## Lastprofil per last

I utviklingsversjonen velger du **Av**, **Historikk (siste sju dager)** eller **Manuell** ved oppretting/redigering av last. Historikk krever effektsensor i recorder. Manuell krever navn, nominell effekt og arbeidssyklus; typisk påtid er valgfri. Uten effektmåling er profilen bare et planleggingsanslag.

Sett maksimal kuttvarighet etter lasten og blueprinten. **Bruk lastprofiler i kuttvurderingen** er av som standard; på bruker energi-estimatet for målte aktive laster. Se [lastprofiler](lastprofiler.md#profiler-inne-i-home-assistant).
