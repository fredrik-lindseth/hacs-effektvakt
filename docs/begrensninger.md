# Begrensninger

## 60-sekunders tick i lav-risiko-modus

Rolig drift sjekkes hvert 60. sekund, høy risiko hvert 15.–30. sekund. En brå effektøkning nær timeskiftet kan oppdages for sent til å kutte.

## Et kutt uten effektmåling er et sjansespill

Nominell effekt sier ikke om lasten varmer nå eller hvor lenge den ellers ville fortsatt. Bruk [målt effekt](laster.md) for tilgjengelig kutt og [lastprofiler](lastprofiler.md) for et energianslag. Manuelle profiler uten wattmåling gir bare planleggingsanslag.

## De første dagene av måneden er vakten for streng

Standardmålet er billigste trinn måneden fortsatt kan ende på. Tidlig i måneden kan dette være lavere enn huset vanligvis klarer. Kuttkriteriet demper rådene for timer som ennå ikke låser inn en kostnad. Et valgt [månedsmål](sparepotensial.md#et-mål-for-måneden) kan gi et mer relevant tak, men også tidligere og flere kutt.

## DSO-data er statisk

Innebygde tariffer følger versjonen av [fri-nettleie](https://github.com/kraftsystemet/fri-nettleie) som repoet har hentet. Nye priser krever oppdatering; egendefinerte trinn må du vedlikeholde selv. Se [tariffgrunnlaget](dso.md).

## HA-restart mister hysterese-pending-state

Risikonivået lagres, men nedtelling for ventende nedgang starter på nytt etter restart. Et høyt nivå kan derfor bli stående lenger. Lastvernets gjeninnkoblingsansvar lagres separat.

## Energy-sensor mangler: dårligere nøyaktighet tidlig i timen

Uten energimåler bygger timeregnskapet bare på effektintegrasjon. Projeksjonen er særlig følsom for kortvarige laster tidlig i timen. En [energimåler](input-sensorer.md#energy-sensor-anbefalt) korrigerer anslaget.

## Ingen historikk mellom instanser

Data lagres per `entry_id`. Sletter og oppretter du integrasjonen på nytt midt i måneden, mangler tidligere døgnmaks i det nye oppsettet.

## Lastprofil er et anslag for planlegging

Profilen bruker siste uke eller manuelle antakelser. Tilstandsdekning beviser ikke ferske eller korrekte sensorer. Den kan valgfritt brukes i kuttvurderingen for målte aktive laster, men velger ikke enkeltlaster eller planlegger gjenoppvarming. Se [metodikken](lastprofiler.md).
