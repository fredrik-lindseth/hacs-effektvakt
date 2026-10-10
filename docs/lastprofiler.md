# Lastprofiler

En lastprofil beskriver hvor ofte en last trekker strøm, effekten mens den er på og hvor lenge den pleier å fortsette. Vi bruker siste uke som et beste anslag for neste uke og oppdaterer anslaget med nyere observasjoner. Profilen gjør det lettere å velge et kutt som bidrar nok i timen uten å slå av mer enn nødvendig.

## Effekt, påandel og energi

2 000 W med 15 % arbeidssyklus gir 300 W i gjennomsnitt, eller 0,3 kWh per gjennomsnittstime. Momentant kutt kan være 2 kW når lasten er på. Kuttenergien avhenger av hvor lenge den ellers ville gått.

300 W i tjue minutter bidrar med 0,1 kWh; i fem minutter er bidraget 0,025 kWh. Bruk kjent påtid og sammenlignbare sykluser til å anslå restvarighet. Manuell nominell effekt og arbeidssyklus merkes som antakelser. Tell hver fysisk last én gang.

## Profiler inne i Home Assistant

Utviklingsversjonen har et profilvalg per kuttbar last under Konfigurer. Velg **Av**, **Historikk (siste sju dager)** eller **Manuell**. Automatisk profil bruker de siste sju dagene i recorder-historikken og oppdateres i bakgrunnen hver time. Effektsensoren må være med i recorder-historikken. Ved recorder-feil beholdes siste profil med feilstatus og opprinnelig tidspunkt. Profiler eldre enn 24 timer brukes ikke i anslaget.

For en manuell profil oppgir du nominell effekt i W og arbeidssyklus i prosent. Typisk påtid er valgfri. En navngitt manuell last kan legges inn uten effektsensor, for eksempel gulvvarme med kjent installert effekt. Da bidrar den med et anslag for planlegging og telles ikke som målt tilgjengelig kutt. Climate-entiteter kan knyttes til lasten som aktuator; `heat`-modus tolkes aldri som målt aktiv oppvarming.

Sett maksimal kuttvarighet etter hva lasten tåler og tidsgrensen i blueprinten; profilens standard er seksti minutter. Feltet begrenser anslaget og erstatter ikke lastvernets gjeninnkoblingsfrist.

`sensor.effektvakt_estimert_kuttenergi_resten_av_timen` viser estimert kuttenergi i kWh og opprettes når minst én last har profil aktivert. `sensor.effektvakt_tilgjengelig_kutt` viser fortsatt målt momentan effekt i kW. Attributtene per last viser profilkilde, datagrunnlag, dekning, aktiveffekt og støttende sykluser. Ukjent grunnlag skilles fra null bidrag.

**Bruk lastprofiler i kuttvurderingen** er av som standard. Slår du den på, brukes estimert energi fra målte laster som er aktive akkurat nå til å vurdere om et kutt kan hjelpe. Laster uten profil beholder den eksisterende antakelsen om tilgjengelighet resten av timen. Manuelle profiler uten effektmåling forblir planleggingsanslag og gir aldri kapasitet til automatisk styring. Automatisk valg av enkeltlaster og plassering av gjenoppvarming gjenstår.

## Kjør analysen selv

Fra repo-roten kan du kjøre verktøyet med repoets unit-miljø gjennom `uv`, uten Home Assistant. Selve analyseverktøyet bruker bare standardbiblioteket og krever Python 3.11 eller nyere. Lag en lokal `profil.json` med tidspunkt og effekt i W. Eksemplet er kunstig og har én hel påperiode på tjue minutter:

```json
{
  "punkter": [
    {"tid": "2026-01-01T00:00:00+01:00", "watt": 0},
    {"tid": "2026-01-01T00:10:00+01:00", "watt": 300},
    {"tid": "2026-01-01T00:30:00+01:00", "watt": 0},
    {"tid": "2026-01-01T01:00:00+01:00", "watt": null}
  ],
  "vinduer": [["2026-01-01T00:00:00+01:00", "2026-01-01T01:00:00+01:00"]]
}
```

```bash
uv run --group unit python scripts/analyser_lastprofil.py profil.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-01T01:00:00+01:00 --terskel-w 100 --allerede-paa-minutter 10 --minst-videre-minutter 5 > rapport.json
```

Rapporten viser 100 Wh energi, 33,3 % påandel, 300 W aktiveffekt og én hel syklus. Restvarighetsanslaget har bare én støttende syklus i dette eksemplet. `vinduer` er valgfritt og kan inneholde de faktiske topptimene i huset. Da kan du sammenligne lastens aktivitet i disse timene med aktiviteten over hele måleperioden.

Hent historikken til effektsensoren fra Home Assistant, og gjør tilstandene om til dette formatet. Ta med tilstanden som gjaldt ved starten av vinduet og alle endringene fram til slutten. Normaliser kW til W ved å gange med 1 000. `unknown`, `unavailable` og verdier som ikke kan leses, blir `null`. Tidspunktene må ha tidssone. Oppbevar egne rådata lokalt; en rapport som deles bør utelate entitets-id-er og opplysninger om huset.

## Eksporter historikken fra Home Assistant

Opprett et langvarig tilgangstoken i brukerprofilen din i Home Assistant. Kjør eksportverktøyet lokalt; erstatt adresse, sensor og datoer med dine egne. Verktøyet spør etter tokenet uten å vise det eller legge det i shell-historikken:

```bash
uv run --group unit python scripts/hent_lastprofil.py --url https://ha.example --sensor sensor.example_power --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --utfil profil.json
uv run --group unit python scripts/analyser_lastprofil.py profil.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --terskel-w 100 > rapport.json
```

Eksporten bruker HA-endepunktet `/api/history/period` med valgt sensor, initialtilstand og fulle attributter. W og kW normaliseres til W, mens ukjente eller ugyldige verdier beholdes som `null`. Tidspunktene skrives i UTC. Bare `tid` og `watt` lagres; entitets-id-er, sensorens navn og tokenet utelates. Hold filen lokal, siden selve effekthistorikken kan si noe om vanene i huset.

`HA_URL` kan gi adressen i stedet for `--url`. For kjøring uten interaktiv prompt kan `HA_TOKEN` komme fra et eksisterende hemmelig miljø; token støttes ikke som kommandolinjeargument. `--timeout` er seksti sekunder som standard. Omdirigering avvises, så bruk den endelige HA-adressen. Tom historikk kan skyldes at sensoren er utelatt fra recorder, gamle data er slettet eller tokenet mangler lesetilgang. Verktøyet kan ikke gjenskape manglende målinger.

## Slik regner verktøyet

Hver registrerte tilstand gjelder fram til neste registrerte endring. Energi og påandel vektes etter varighet, ikke antall datapunkter. Effekten må være strengt over valgt terskel for å regnes som aktiv. Velg terskelen over standby, men under vanlig aktiveffekt.

Ukjente intervaller holdes utenfor kjent energi og påandel. `dekning` er kjent tid delt på hele målevinduet. Historikk med få endringer kan ha høy dekning fordi verdier holdes videre; det beviser ikke at sensoren er fersk. Bruk `--maks-hold-sekunder 600` hvis en tilstand skal bli ukjent etter ti minutter uten ny rapport. Velg grensen etter hvordan akkurat denne sensoren rapporterer; en sensor som bare rapporterer ved endring trenger en annen vurdering enn en som sender hvert minutt.

En påperiode som begynte før vinduet, fortsetter etter vinduet eller avbrytes av ukjent effekt, har ukjent full varighet. Den regnes med i kjent aktivitet, men holdes utenfor restvarighetsanslaget. Bare hele sykluser som er minst like lange som den aktuelle påperioden, støtter anslaget. Rapporten viser antallet. Å utelate ufullstendige sykluser kan gi overvekt av korte sykluser, særlig i korte målevinduer.

Varighet beregnes i faktisk tid med tidssone. Ved sommertidsskiftet er to lokale 02-timer forskjellige timer. Bruk de tidsstemplede vinduene som svarer til målerens klokketimer når du undersøker topptimer.

## Bruk profilen til å spare

Sammenlign energien som må bort fra timen med bidraget fra aktive laster innenfor tillatt utkobling. Behold temperaturbehov, frister og minste påtid. Koble til riktig aktuator, så egne kutt holdes utenfor læringen.

Utsatt forbruk må få plass senere uten en ny topp. Flytting av kWh er ikke i seg selv spart energi; redusert kapasitetstrinn er spart nettleie. Se [simuleringen](sparepotensial.md#regneeksempel-og-simulert-styring). Analyseverktøyet kobler ikke ut laster.
