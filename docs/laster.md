# Kuttbare laster

En kuttbar last er forbruk du kan utsette innenfor lastens behov og tidsgrenser: varmtvann, oppvarming eller lading. Velg grensene etter lasten, ikke etter et felles løfte om en halvtime uten ulempe. Effektvakt bruker sensor, aktuator og terskel til å beskrive den.

| Felt             | Krav    | Hva den brukes til                                                    |
| ---------------- | ------- | --------------------------------------------------------------------- |
| Effektsensor     | Påkrevd, unntatt manuell profil | Hvor mye lasten trekker akkurat nå |
| Bryter/aktuator | Valgfri | Kobler lasten til den samme switchen eller climate-entiteten som styringen bruker |
| Terskel (W)      | Påkrevd | Hvor mye den må trekke for å regnes som på. Standard 100 W            |
| Navn             | Valgfri | Vises i varsler og på dashbordet. Står det tomt, brukes sensorens navn |

Lastene legges inn under **Settings > Devices & Services > Effektvakt > Configure > Legg til en kuttbar last**. Der ligger også redigering og fjerning. Alt lagres med en gang, så du kan lukke dialogen når du er ferdig.

## Terskelen

Terskelen skiller «varmer nå» fra standby. Den er per last fordi lastene er ulike:

| Last                   | Typisk effekt når på | Fornuftig terskel |
| ---------------------- | -------------------- | ----------------- |
| Varmtvannsbereder      | 2 000 W              | 1 000 W           |
| Varmepumpe             | 800-2 500 W          | 400 W             |
| Varmekabler, bad       | 400-600 W            | 100 W             |
| Panelovn               | 600-1 500 W          | 100 W             |
| Billader               | 3 600-22 000 W       | 1 000 W           |

Velg terskel over standby og under aktiveffekt.

Terskelen er streng: nøyaktig på terskelen holder ikke, det må være over.

## Bryteren

Aktuatoren er valgfri for måling, men koblingen gjør det mulig å sammenligne effekt med styring. Blueprintene ber integrasjonen om kutt gjennom `effektvakt.styr_last`; lastvernet eier gjeninnkobling, originaltilstand, frister og minste påtid. Bare laster vernet faktisk har overtatt, regnes som styrt av Effektvakt. En bryter som går av samtidig med et kuttvarsel beviser ikke alene at Effektvakt slo den av.

En climate-entitet kan brukes som aktuator for varmekabler eller annen termostatstyrt varme. Modusen `heat` viser at oppvarming er tillatt; den sier ikke at elementet trekker strøm akkurat nå. En utilgjengelig aktuator gir ukjent tilstand, ikke bekreftet utkobling.

Legg inn den samme bryteren her som blueprinten din styrer. Har lasten en smartplugg med effektmåling, er effektsensoren og bryteren to entiteter fra den samme pluggen.

## Hva sensoren viser

`sensor.effektvakt_tilgjengelig_kutt` er summen av lastene som trekker over terskelen sin akkurat nå. Har du ingen laster med effektsensor, opprettes ikke sensoren i det hele tatt. Manuelle profiler uten måling vises gjennom sensoren for estimert energi.

Attributtet `kutt_kilder` har én oppføring per konfigurert last, så et dashbord kan vise hva som faktisk er kuttbart framfor bare summen. Feltene er dokumentert i [sensorer.md](sensorer.md#kutt_kilder).

Alle konfigurerte laster står i lista, også de som ikke teller akkurat nå. Forskjellen mellom «finnes ikke» og «teller ikke nå» er nettopp det som er verdt å se. En last får `teller_med: false` når sensoren er utilgjengelig, eller når effekten ligger på eller under terskelen. Er sensoren utilgjengelig, er `effekt_w` null og ikke 0: da vet vi ikke hva lasten trekker.

## Et eksempel

| Last              | Effekt når aktiv | Terskel | Bidrag til kutt |
| ----------------- | ---------------- | ------- | --------------- |
| Varmtvannsbereder | 2 000 W          | 1 000 W | 2,0 kW          |
| Varmekabler bad   | 550 W            | 100 W   | 0,55 kW         |
| Varmekabler stue  | 900 W            | 100 W   | 0,90 kW         |
| Panelovn          | 1 200 W          | 100 W   | 1,2 kW          |
| **Sum**           |                  |         | **4,65 kW**     |

Summen gjelder mens alle fire laster er aktive. Energi som kan flyttes avhenger også av varighet.

## Sammenhengen med blueprintene

Blueprintene bruker `binary_sensor.effektvakt_kutt_ned_anbefalt` som trigger, ikke `tilgjengelig_kutt`. Varsel-blueprinten leser `kutt_kilder` for å foreslå hvilken last du skal slå av, og velger den største som teller med akkurat nå.

Vil du at en automasjon bare skal kutte når det finnes noe å kutte, kan du legge til en betingelse:

```yaml
condition:
  - condition: state
    entity_id: binary_sensor.effektvakt_kutt_ned_anbefalt
    state: "on"
  - condition: numeric_state
    entity_id: sensor.effektvakt_tilgjengelig_kutt
    above: 0.5
```

Det slår bare av lasten hvis Effektvakt anbefaler kutt og det er minst 0,5 kW å hente.

## Fra strategier til laster

Oppsett fra før entry-versjon 2 migreres automatisk: VVB-sensoren blir en last med 1 000 W terskel, ekstra sensorer får 100 W, og strategien fjernes. Ingen aktuator kunne migreres; legg inn samme bryter eller climate-entitet som styringen bruker under Konfigurer.

## Lastprofiler

Velg historikk eller manuell profil per last. Manuell profil uten wattmåling gir bare et planleggingsanslag. Maksimal kuttvarighet må stemme med blueprintens grense. Se [metode og bruk](lastprofiler.md) og [sensorattributtene](sensorer.md#lastprofiler-og-estimert-kuttenergi).
