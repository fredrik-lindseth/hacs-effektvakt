# Kuttbare laster

En kuttbar last er noe du kan slå av en halvtime uten at noen merker det: en varmtvannsbereder, en varmepumpe, en billader, et sett varmekabler, en panelovn. Effektvakt kjenner ingen apparattyper. Det den trenger å vite om en last er tre ting.

| Felt             | Krav    | Hva den brukes til                                                    |
| ---------------- | ------- | --------------------------------------------------------------------- |
| Effektsensor     | Påkrevd | Hvor mye lasten trekker akkurat nå                                    |
| Bryter           | Valgfri | Lar Effektvakt se at lasten faktisk ble slått av                      |
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

Et berederelement er enten fullt på eller av, så alt mellom 0 og 1 000 W der er standby og ikke oppvarming. Varmekabler på 550 W ville aldri kommet over en slik terskel, og hadde forsvunnet ut av regnestykket hvis terskelen var felles. Det var nettopp det som skjedde fram til september 2026, da integrasjonen hadde to faste terskler: 1 000 W for «VVB» og 100 W for alt annet.

Terskelen er streng: nøyaktig på terskelen holder ikke, det må være over.

## Bryteren

Bryteren er valgfri, men den er det som gjør at Effektvakt vet hva som faktisk skjedde. Det er blueprintene, ikke integrasjonen, som slår av last. Uten bryteren kan integrasjonen bare si hvor mye som er kuttbart; med den ser den at lasten gikk av, når det skjedde, og hvor mye den trakk rett før.

Regelen for at et kutt regnes som Effektvakt sitt: bryteren gikk fra på til av i et øyeblikk der kutt var anbefalt. Slår du av berederen selv en søndag med god margin, er det ikke vår innsparing. En bryter som er `unavailable` endrer ingenting, for da vet vi ikke hva som skjedde.

Legg inn den samme bryteren her som blueprinten din styrer. Har lasten en smartplugg med effektmåling, er effektsensoren og bryteren to entiteter fra den samme pluggen.

## Hva sensoren viser

`sensor.effektvakt_tilgjengelig_kutt` er summen av lastene som trekker over terskelen sin akkurat nå. Har du ingen laster, opprettes ikke sensoren i det hele tatt. Det er et ærligere svar enn et tall: fram til september 2026 stod den på 0,3 kW hele døgnet for alle som ikke hadde valgt en strategi, og tallet var en antagelse om en varmtvannsbereder ingen visste om brukeren hadde.

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

Med 4,65 kW tilgjengelig kutt er det god margin mot de fleste trinngrenser, og du kan bruke sensoren til å avgjøre hvilke laster det faktisk er nødvendig å slå av.

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

Fram til entry-versjon 2 hadde konfigurasjonen i stedet en kutt-strategi (`blind`, `vvb_status`, `vvb_pluss_ekstra`), ett felt for VVB-effektsensor og ett for ekstra sensorer. Strategien styrte bare hva `tilgjengelig_kutt` viste, ingen blueprint leste den, og med `blind` var sensoren en konstant 0,3 kW.

Oppsett fra den tiden migreres automatisk ved første oppstart: VVB-sensoren blir en last med 1 000 W terskel, hver ekstra sensor blir en last med 100 W, og strategien forsvinner uten erstatning. Sensorene beholdes uansett hvilken strategi som stod valgt, siden en sensor du har pekt på er en last du har. Migreringen setter ingen bryter, for det fantes ikke noe å migrere fra: skal Effektvakt se kuttene dine, må du legge inn bryteren selv under Configure.
