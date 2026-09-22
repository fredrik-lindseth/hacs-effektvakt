# Effektvakt-kortet

Kortet er den gamle effektvakta som satt i sikringsskapet, satt inn i Lovelace.
Tre visere på samme nav: en tykk rød for projisert time-snitt, en tynn svart for
effekten akkurat nå, og et lite slepemerke på utsiden av buen for topp-3-snittet
denne måneden. Utenfor skalaen ligger kapasitetstrinnene som buesegmenter med
kr/mnd trykt under, og kortet merker trinnet måneden ligger an til og det neste.

Kortet følger med integrasjonen. Ingen HACS-plugin og ingenting å laste ned:
filene under `custom_components/effektvakt/www/` serveres på `/effektvakt-static`,
og integrasjonen melder URL-en inn i Lovelace sine ressurser selv når HA starter.
Er integrasjonen installert, ligger «Effektvakt» i kortvelgeren.

## Legg det inn

```yaml
type: custom:effektvakt-card
entity: sensor.effektvakt_projisert_time_snitt
tittel: Effektvakt
```

Det er alt som trengs. Resten finner kortet selv.

## Konfigurasjon

| Nøkkel           | Påkrevd | Hva det gjør                                                     |
| ---------------- | ------- | ---------------------------------------------------------------- |
| `entity`         | ja      | Sensoren for projisert time-snitt. Den rød viseren, og kilden til øyeblikkseffekten (`current_kw`). |
| `kostnad_entity` | nei     | `sensor.effektvakt_kostnad_neste_trinn`. Finnes automatisk på samme enhet. |
| `maks_kw`        | nei     | Skalaens toppverdi. Standard 15, rundes opp til nærmeste multiplum av 15. |
| `stil`           | nei     | `geha` (standard) eller `gossen`. Se under.                       |
| `tittel`         | nei     | Overskrift over skiven. Utelatt gir ingen overskrift.             |

Det finnes en visuell editor med entitetsvelger, skalavalg og stilvalg, så YAML
er ikke nødvendig.

## Hva står på skiven

Skiven har to slags merker, og de må ikke blandes. Noen er lagt der av oss og
betyr noe for avlesningen. Resten er originalens egne instrumentmerker, som er
med fordi vi gjenskaper et ekte instrument.

### Avlesningen

| Merke | Hva det er |
| ----- | ---------- |
| Kort, tykk rød viser | Projisert time-snitt: der timen ender hvis forbruket fortsetter som nå. Hovedavlesningen. |
| Tynn, lang svart viser | Effekten akkurat nå. |
| Liten trekant utenfor buen | Slepemerket. Står på topp-3-snittet for måneden og går aldri ned igjen, så det er nivået du betaler for uansett hva du gjør resten av måneden. |
| Kr-båndet ytterst | Kapasitetstrinnene med månedspris. Trinnet måneden ligger an til er tykt, neste trinn er rødt. |
| «---»-flagg midt i skiven | Ingen avlesning. Viserne står parkert på null. Linjen under skiven sier om sensoren er borte eller om Effektvakt ennå ikke har en måling. |

Trekanten er den eneste som ikke sier seg selv, og den er verdt å lære: en rød
viser som står lavt betyr ingenting hvis slepemerket allerede står i neste
trinn.

### Originalens instrumentmerker

Disse kommer fra målerskivene panelet er tegnet etter, og forteller hva slags
instrument det er. De er trykt fast og endrer seg aldri.

| Merke | Hva det betyr |
| ----- | ------------- |
| ∩ med strek under | Dreispoleverk. Lineær skala. Skiven `geha` bruker denne. |
| ∩ med strek inni | Dreiejernverk. Ikke-lineær skala, trykket sammen mot toppen. Skiven `gossen` bruker denne. |
| ∼ | Vekselstrøm. |
| ⊥ | Instrumentet skal henge loddrett. Tyngdekraften på viser og opphenget påvirker nøyaktigheten, så bruksstillingen er en del av spesifikasjonen. |
| KL.1,5 | Nøyaktighetsklasse 1,5, altså halvannen prosents feilmargin av full skala. |
| Stjerne med tall i | Isolasjonsprøvespenning i kilovolt. En 2-er betyr at instrumentet er prøvd på 2 kV. |
| «100 mA» | Verket originalen satt på: Gossen-skiven er tegnet etter et instrument med 100 milliampere fullutslag. Står bare på trykkfilen. |

Kilden er Fredrik og en kollega av ham, ikke nettet. Symbolene er standardisert
i IEC 60051, men den står bak betalingsmur, så dette er skrevet ned her nettopp
fordi det ikke lar seg slå opp fritt.

«100 mA» er tatt av kortet og står bare igjen på trykkfilen. Den sier noe om
måleverket originalen satt på, ingenting om avlesningen, og alle som ikke hadde
lest dette avsnittet spurte hva den betydde. På plata i sikringsskapet hører den
hjemme, der den er en del av instrumentet.

Trykt tekst ligger i lommene mellom viseren sine ytterstillinger og bunnfeltet,
ikke i banen viserne sveiper over. Verksnavnet sto en stund midt under «KW» og
ble lest som «EHA-METER» når den røde kilen la seg over G-en; nå står det nede
til høyre sammen med klassemerket. Enheten er den eneste som ligger i sveipet,
slik originalene har den. `test_trykt_tekst_ligger_utenfor_viserens_sveip`
regner på det ved hver kjøring, så en ny tekstlinje i feil lomme feller bygget.

## To skiver

`geha` er en GEHA-METER med dreispoleverk: lineær skala, jevne hovedtall,
kremhvit emalje. `gossen` er en Gossen med dreiejernverk, der skalaen er trykket
sammen mot toppen og har en sokkel nederst så de laveste kapasitetstrinnene blir
med. Stilene kommer fra registeret i `faceplate.py`, ikke fra en liste i kortet,
så en ny skive der dukker opp i stilvelgeren av seg selv.

## Hvorfor kortet ikke tegner skalaen

Skiven kommer ferdig som SVG over websocket-kommandoen `effektvakt/faceplate`,
generert av `faceplate.py`. Det er samme fil som lager trykkfilen til det
fysiske panelet, så kortet og plata kan ikke drifte fra hverandre. Kortet leser
geometrien av data-attributtene på svg-rota (`data-vinkel-start`,
`data-skala-eksponent`, `data-skala-sokkel-kw` og resten) og regner viservinkelen
derfra. Skalaformen ligger altså ett sted, i Python, og kortet gjenskaper den
ikke.

Fargene kommer samme vei. `faceplate.py` har en palett med rollenavn (`emalje`,
`trykk`, `viserrod`, `krom-lys`, `krom-mork`, `skygge`, `prisme-lys`,
`prisme-mork`, `prisme-glans`), og websocket-svaret sender dem med. Kortet
setter dem som CSS custom properties med prefiks `--effektvakt-`. Reserven som
står i `:host` i kortet brukes bare hvis svaret mangler en rolle.

## Slepemerket er ekte max-hold

Slepemerket speiler ikke sensoren. `top_n_average` deler på antall dager og ikke
alltid på tre, så topp-3-snittet kan gå ned igjen tidlig i måneden: to dager på
12 kW gir 12, og en rolig tredje dag drar snittet til 8,17. En slepeviser som
synker ser ødelagt ut.

Kortet holder derfor høyeste verdi det har sett, og nullstiller ved månedsskifte.
Verdien lagres i nettleserens `localStorage` per entitet, ellers ville merket
falt tilbake til sensorverdien hver gang dashbordet lastes, og da er max-hold
verdiløst. Er lagringen utilgjengelig, som i privat modus, lever merket bare i
den økten.

Merk at merket er per nettleser. Åpner du dashbordet på telefonen for første gang
midt i måneden, starter max-hold der på den verdien sensoren har da.

## Når det ikke er noen avlesning

Alle tre viserne parkeres på null og et lite «---»-flagg legger seg midt i
skiven. En frossen viser som ser ut som en avlesning er verre enn en tom skive.

Kortet skiller mellom to grunner, for de betyr ikke det samme:

- `unavailable` er en sensor som er borte. Linjen under skiven navngir entiteten.
- `unknown`, eller en tilstand uten attributtet `current_kw`, er en integrasjon
  som ikke har noen måling å gi ennå. Det skjer rett etter omstart, og etter at
  watchdogen har tømt coordinatoren. Da står det at Effektvakt ikke har en måling
  å vise.

Det siste er poenget med flagget: «0,00 kW» er en måling av et hus som ikke
bruker strøm, og det er noe helt annet enn at vi ikke vet.

## Skiven hentes med gjenforsøk

Websocket-kommandoen `effektvakt/faceplate` registreres når integrasjonen settes
opp, og ved omstart av Home Assistant skjer det etter at frontenden har koblet
seg på. Kortet som spør for tidlig får «Unknown command» tilbake. Derfor prøver
det igjen med voksende pause (et halvt sekund, så 1, 2, 4, 8, 15 og til slutt 30
sekunder mellom forsøkene) og står med en nedtonet «Henter skiven …» imens.
Først fra femte forsøk, rundt femten sekunder ut, blir meldingen rød og sier hva
Home Assistant svarte. Forsøkene stopper når kortet tas ut av dashbordet og tas
opp igjen når det settes inn.

## Tilgjengelighet

Skiven er `role="img"` med en `aria-label` som leser av alle tre verdiene i
klartekst, oppdatert hver gang tallene endrer seg. Trinnbåndet finnes bare som
grafikk, så det har et eget skjult tekstalternativ som sier hvilket trinn måneden
ligger an til, hva det koster, og hva det neste koster. Tallene som står synlig
under skiven er `aria-hidden`, siden de er en gjentakelse av aria-etiketten og
ellers ville blitt lest to ganger.

Viserne har en myk overgang med et lite oversving, slik et dreispoleverk faktisk
oppfører seg. Den slås av under `prefers-reduced-motion`.

## Prøvebenk for utvikling

`docs/kort-harness/` kjører kortet uten Home Assistant, så du slipper å rote i
en produksjonsinstallasjon for å se om en endring virker:

```bash
python3 docs/kort-harness/server.py
```

Den serverer repoet på `http://127.0.0.1:8799/docs/kort-harness/` og åpner
nettleseren. `--dso sygnir` gir et annet nettselskap, `--port` en annen port og
`--ingen-nettleser` lar være å åpne noe.

Benken laster den ene ekte kortfilen fra
`custom_components/effektvakt/www/effektvakt-card.js`. Det ligger ingen kopi
under `docs/`, for da ville de to drevet fra hverandre og benken begynt å lyve.
Skivene kommer heller ikke fra en frossen JSON-fil: `server.py` genererer dem
fra `faceplate.py` ved hver forespørsel, så en endring i skiven vises ved neste
oppfriskning.

Fem kort tegnes: begge stilene, en 30 kW-skala, et kort med en entitet som ikke
finnes og et der sensoren ikke har noen måling ennå, så begge grunnene til
«---»-flagget kan sjekkes. `?sen=3000` lar websocket svare «Unknown command» de
tre første sekundene, slik Home Assistant gjør rett etter omstart, og da kan
gjenforsøkene prøves uten å restarte noe. Konsollen skriver ut aria-etiketten,
det skjulte tekstalternativet, alle ni fargerollene, hvilke trinn som ble merket
og viservinklene.

Testdataene, altså de oppdiktede sensorverdiene, ligger i `tilstander` og
`oppsett` i `docs/kort-harness/index.html`. Skru på tallene der for å prøve
andre avlesninger. Vil du ha andre kapasitetstrinn, bytt nettselskap med
`--dso`; trinnene leses fra `dso.py` og er alltid de ekte.

Lys og mørk modus følger operativsystemet, siden benken bruker
`prefers-color-scheme` slik Home Assistant gjør.

## Ressursen i Lovelace

Integrasjonen legger `/effektvakt-static/effektvakt-card.js?v=<versjon>` inn som
en modul-ressurs i Lovelace, samme sted HACS legger sine kort. Det må være der:
Lovelace laster ressursene sine før dashbordet tegnes, mens et løst `import()`
i index-HTML-en ingen venter på, taper kappløpet mot resten av siden. Uten
ressursen kommer kortet opp som «Konfigurasjonsfeil» hver gang cachen er kald.

Registeret er ditt, ikke vårt, så integrasjonen tar i det så lite som mulig.
Oppføringen legges inn én gang, oppdateres når `?v=` endrer seg ved en
oppgradering framfor å få en ny ved siden av, og fjernes igjen når du sletter
Effektvakt-oppsettet. Har du flere oppsett, blir den stående til det siste er
borte. Reload av oppsettet og omstart av HA skriver ingenting.

Kjører Lovelace med ressurser fra `configuration.yaml`, kan ingen integrasjon
skrive der. Da faller vi tilbake på `add_extra_js_url` og logger en advarsel, og
kortet tegnes bare pålitelig hvis du selv legger inn:

```yaml
lovelace:
  resources:
    - url: /effektvakt-static/effektvakt-card.js?v=0.3.0
      type: module
```

`?v=` må stemme med `version` i `custom_components/effektvakt/manifest.json`, og
må oppdateres for hånd ved oppgradering. Det er prisen for YAML-modus.

## Feilsøking

**Kortet finnes ikke i velgeren, eller står som «Konfigurasjonsfeil».** Sjekk at
ressursen ligger i Innstillinger → Dashbord → Ressurser. Er den ikke der, kjører
du trolig Lovelace med YAML-ressurser; se avsnittet over. Ellers holder det
vanligvis med en hard refresh, siden URL-en har `?v=<versjon fra manifest.json>`
som cache-buster.

**«Fikk ikke hentet skiven».** Meldingen kommer først etter rundt femten
sekunder med gjenforsøk, så den betyr noe. Står det «Unknown command», er integrasjonen
ikke lastet: sjekk loggen for en oppstartsfeil. Ellers fant websocket-kommandoen
ingen Effektvakt-oppsett for entiteten, og da skal `entity` sjekkes mot
integrasjonen, eller det er flere Effektvakt-oppsett enn ett.

**Ingen trinn er merket.** Kostnadssensoren mangler eller er utilgjengelig. Sett
`kostnad_entity` uttrykkelig hvis autodeteksjonen ikke treffer, for eksempel hvis
du har flere Effektvakt-oppsett.

**Slepemerket står for høyt.** Det er max-hold. Det går ned ved månedsskifte, og
ellers ved å tømme `localStorage` for HA-adressen.
