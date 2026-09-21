# Fysisk panel

GEHA-METER som ekte dings på veggen: et dreispoleinstrument der viseren faktisk
beveger seg, drevet av en ESP32 som leser
`sensor.effektvakt_projisert_time_snitt` fra Home Assistant. Ingen skjerm som
later som den er et instrument. Oppskriften ligger i
[`esphome/effektvakt-panel.yaml`](../esphome/effektvakt-panel.yaml), skiven
kommer fra `scripts/export_faceplate.py`, og alt under er svakstrøm.

> **Status**: konfigurasjonen validerer med esphome 2026.5.1, men panelet er
> ikke bygget. Maskinvaren er ikke kjøpt, så ingenting her er prøvd på ekte
> instrument. Motstandsverdiene er regnet, ikke målt.

---

## Hva originalen målte

Originalen er et strøminstrument. På skiven står 230V og 43.4B/0.1A, og
instrumentet henger på en strømtransformator rundt inntaket. Den måler altså
ampere, og kW-tallene er trykket på skalaen under antakelsen om at spenningen er
230 V og effektfaktoren 1. Svinger spenningen, eller er lasten reaktiv, viser
den feil, og feilen er usynlig fordi skalaen sier kW.

Vår utgave arver ikke den feilkilden. ESP32-en får effekten fra Home Assistant,
altså fra AMS-måleren som måler ekte watt, og oversetter tallet til et utslag på
viseren. Tallene på skalaen er reelle kW. Det er også forklaringen på at skiven
ser ut som et strøminstrument: utseendet er arvet fra originalen, målemetoden er
ikke.

---

## Deleliste

| Del | Spesifikasjon | Merknad |
| --- | --- | --- |
| Dreispoleinstrument | Analogt panelmeter, DC, fullutslag 0-1 mA | Hjertet i dingsen. Se kravene under. |
| ESP32-utviklingskort | Klassisk ESP32 (WROOM/WROVER) eller ESP32-S2 | Må ha DAC. C3, C6 og S3 har det ikke. |
| Fastmotstand | 2,2 kΩ, 1/4 W, metallfilm | I serie med instrumentet. |
| Trimpotensiometer | 2 kΩ, flerdreid (25 omdreininger) | Fullskala-trim. Endreid duger, men blir fikling. |
| Strømforsyning | USB 5 V, 1 A, med kabel | ESP32-en trekker lite, men vil ha stabil 5 V. |
| Koblingsbrett | Liten stripeboard eller skrueterminaler | Tre komponenter, trenger ikke kretskort. |
| Kabinett | Originalt meterhus, trekasse eller ABS-boks | Skiven er tegnet 100 mm kvadratisk. |
| Utskrift av skiven | Matt fotopapir 200 g, eller trykk på aluminium | Fra `export_faceplate.py`, se under. |
| Spraylim | 3M 77 eller tilsvarende | Skiven limes på en stiv plate. |
| Materiale til pekepinnen | 0,3-0,5 mm svart styren eller messingstrimmel | Den manuelle viseren, se eget avsnitt. |
| Smådeler | M2-skrue med nylonskive, avstandsstykker, veggfeste | |

### Krav til instrumentet

Det som må stemme er at det er et dreispoleinstrument (ikke dreiejern, ikke
digitalt), at det går på likestrøm, og at fullutslag er 1 mA eller mindre. Alt
av skalatrykk på det du kjøper er likegyldig, siden skiven byttes uansett.
Brukte panelmetre fra Finn eller en surplusbutikk gir riktigere preg enn nye
kinesiske, og er ofte billigere.

Tre ting bør måles eller sjekkes før du bestiller:

- **Skivestørrelsen.** Tegningen er 100 mm kvadratisk. Er instrumentets skive
  noe annet, skaleres SVG-en ved import i CAD. Den er vektor, så det koster
  ingenting.
- **Hvor akselen sitter.** Skiven har navet 50 mm fra venstre kant og 90 mm fra
  toppen, altså 10 mm over underkanten. Tallene ligger i `data-nav-x` og
  `data-nav-y` på SVG-roten. Sitter akselen på ditt instrument et annet sted,
  må skiven flyttes tilsvarende i CAD.
- **Utslagsvinkelen.** Skalaen på skiven spenner 100 grader, fra -50 til +50 fra
  loddlinjen. Mange firkantede panelmetre går bare 90 grader. Er ditt et
  90-graders instrument, når ikke viseren det siste hovedmerket, og da må
  `VINKEL_SVEIP` i `custom_components/effektvakt/faceplate.py` settes til
  instrumentets faktiske sveip før du trykker skiven. Dette er det eneste
  punktet i hele byggingen der maskinvaren henger sammen med koden.

---

## Kobling

Alt er svakstrøm. Ingenting i dette panelet kobles til nettet, og det henger
ingen strømtransformator rundt inntaket slik originalen gjorde. Effekten kommer
over wifi.

```
ESP32 GPIO25 ──[ 2,2 kΩ ]──[ trimpot 2 kΩ ]──(+) instrument (−)── ESP32 GND
```

DAC-en gir 0 til omtrent 3,3 V. Skal instrumentet stå på fullutslag ved 1 mA, må
total motstand i kretsen være rundt 3,3 kΩ, inklusive instrumentets egen
spolemotstand (typisk 50-500 Ω på et 1 mA-verk). 2,2 kΩ fast pluss 2 kΩ trimpot
gir et område fra 2,2 til 4,2 kΩ, altså margin begge veier.

Koble aldri instrumentet rett på pinnen uten motstanden. 3,3 V over en 1
mA-spole er flere titalls ganger for mye, og verket brenner av på et øyeblikk.

Bruker du ESP32-S2 i stedet for klassisk ESP32, er DAC-pinnene GPIO17 og GPIO18,
og `dac_pin` i YAML-en må endres.

### Oppløsning og oppdatering

DAC-en er 8 bits, altså 256 trinn over hele skalaen. På 15 kW blir det 59 W per
trinn, som er langt finere enn det øyet leser av en 100 mm skive.

Home Assistant oppdaterer sensoren hvert 15. til 60. sekund avhengig av
risikonivå, så viseren gjør et hopp per oppdatering framfor å gli. Dempingen i
verket gjør at hvert hopp lander mykt, så det ser ut som et instrument som
setter seg, ikke som en skjerm som oppdaterer.

---

## Programvare

```bash
cp esphome/secrets.example.yaml esphome/secrets.yaml
$EDITOR esphome/secrets.yaml
esphome config esphome/effektvakt-panel.yaml
esphome run esphome/effektvakt-panel.yaml
```

`secrets.yaml` er gitignorert. `esphome/` er unntatt fra `check-yaml` i
pre-commit, siden `!secret` er en ESPHome-tag som den generiske YAML-sjekken
ikke kjenner.

Enheten dukker opp i Home Assistant som en oppdagbar ESPHome-enhet og legges til
der. Den kommer med fire entiteter: bryteren **Kalibreringsmodus**, tallet
**Kalibreringsnivå**, knappen **Selvtest viser**, og den interne sensoren som
abonnerer på `sensor.effektvakt_projisert_time_snitt`.

To ting er verdt å vite om oppførselen. Mister ESP32-en kontakten med Home
Assistant, legges viseren på null etter senest 30 sekunder. En viser som står
stille på 9 kW fordi forbindelsen er død er verre enn en som står på null, for
den ser ut som en avlesning. Og er sensoren `unavailable`, behandles den på
samme måte.

`maks_kw` i `substitutions` må være det samme tallet som skiven er trykket med.
Står det 15 i YAML-en og skiven er trykket for 30, viser panelet halv verdi uten
å si fra.

---

## Kalibrering

Nullpunktet stilles mekanisk på instrumentet, fullskala stilles med trimpotten.
Begge gjøres med **Kalibreringsmodus** på, som kobler viseren fra HA-verdien så
den ikke rykker midt i arbeidet.

1. Skru trimpotten til maks motstand før du gir strøm første gang. Da kan ikke
   verket få for mye uansett hva DAC-en gjør.
2. Slå på **Kalibreringsmodus** og sett **Kalibreringsnivå** til 0 %. Juster
   nullpunktskruen på instrumentet til viseren står nøyaktig på 0 på skiven.
   DAC-en gir ikke helt rene 0 V ved kode 0, som regel noen titalls millivolt,
   og nullskruen spiser opp akkurat det. Bieffekten er at viseren hviler litt
   til venstre for null når panelet er strømløst. Det er riktig prioritering:
   den skal stemme når den er i bruk.
3. Sett **Kalibreringsnivå** til 100 % og skru trimpotten til viseren står
   nøyaktig på siste hovedmerke, altså 15 kW på en standardskive.
4. Gå tilbake til 0 % og kontroller nullpunktet. De to justeringene påvirker
   hverandre lite, men sjekk uansett.
5. Sett 50 % og se at viseren står på 7,5 kW. Et dreispoleverk er lineært, så
   bommer midten er det skiven som ligger skjevt eller navet som ikke treffer
   akselen. Da hjelper det ikke å skru mer.
6. Slå av **Kalibreringsmodus**. Viseren hopper tilbake til HA-verdien.

### Kryss mot en kjent verdi

Åpne **Utviklerverktøy > Tilstander** i Home Assistant og finn
`sensor.effektvakt_projisert_time_snitt`. Slå på en ovn eller varmtvannsberederen
så tallet flytter seg merkbart, og les av panelet samtidig. Avvik på en
halv delstrek er avlesningsunøyaktighet på en analog skive og helt greit. Avvik som
vokser med utslaget er fullskala som er feil, og rettes med trimpotten. Avvik
som er like stort over hele skalaen er nullpunktet.

Kommer ikke viseren opp til fullskala selv med trimpotten helt nede, er
seriemotstanden for høy, og den faste motstanden må byttes til en lavere verdi.
Går viseren forbi fullskala med trimpotten helt oppe, skrus `dac_maks` i
`substitutions` ned fra 1.0 til for eksempel 0.9. La `dac_maks` stå på 1.0 til
trimpotten er ferdig stilt, ellers trimmer du to ting mot hverandre.

---

## Skiven

Skiven genereres fra `custom_components/effektvakt/faceplate.py`, samme kilde som
dashboard-kortet bruker, så trykk og skjerm kan ikke drifte fra hverandre.

```bash
# Finn din DSO-id
python3 scripts/export_faceplate.py --liste

# Skiven for BKK, klar for trykk
python3 scripts/export_faceplate.py --dso bkk --out geha-bkk.svg

# Med PNG-korrektur ved siden av, 1181 x 1181 piksler som er 300 dpi ved 100 mm
python3 scripts/export_faceplate.py --dso bkk --png
```

`--variant print` er standard og er den du vil ha: flate farger, ingen visere,
ingen slitasje og intet plastdeksel, siden alt det er fysisk på et ekte panel.
`--variant card` er skjermversjonen.

Oppgir du `--maks-kw`, rundes tallet opp til nærmeste multiplum av 15 så
hovedtallene på skalaen forblir hele, og scriptet sier fra når det skjer. Det
samme tallet må stå i `maks_kw` i ESPHome-YAML-en.

Se [development.md](development.md#eksportere-geha-meter-skiven) for detaljene om
scriptet.

### Fra SVG til plate

`viewBox` er `0 0 1000 1000` der én enhet er 0,1 mm, altså 100 mm i faktisk
størrelse. `width` og `height` i filen er uten enhet, så den fysiske størrelsen
settes ved import eller utskrift. I CAD setter du importskalaen, i et
trykkeriverktøy setter du 100 x 100 mm.

Teksten ligger som ekte `<text>`-elementer med en fontstakk, ikke som baner. Den
må konverteres til baner før gravering eller trykk, ellers blir bokstavformene
det maskinen tilfeldigvis har installert. Inkscape finnes ikke på denne
maskinen, så konverteringen gjøres i CAD eller hos trykkeriet.

Skriver du ut selv, bruk matt papir. Blankt papir speiler romlyset og gjør
skiven uleselig fra sofaen. Lim den på en stiv plate, for eksempel 1 mm
aluminium eller det originale skivematerialet, og bor hull for akselen der navet
ligger. Vil du ha det ordentlig, bestiller du trykk direkte på aluminium.

---

## Den svarte viseren

På originalen er den tynne svarte viseren en settbar mekanisk pekepinn, ikke en
måleviser. Den står der brukeren satte den, som en grense å holde seg under. Vår
fysiske utgave gjør det samme: den svarte viseren settes for hånd på neste
trinngrense og står i ro til du bytter trinn eller nettselskap.

Lag den av en 0,3-0,5 mm svart styren- eller messingstrimmel, klipt til så
spissen når skalabuen. Pivoter den på en M2-skrue gjennom dekselet, rett over
instrumentets aksel, med en nylonskive under mutteren så den sitter med friksjon
og kan dreies med en fingertupp. Da ligger den på utsiden av dekselet, nøyaktig
som på originalen.

Grensen finner du i `docs/dso.md` for ditt nettselskap, eller som attributtet
`trinn_na_ovre_grense_kw` på `sensor.effektvakt_kostnad_neste_trinn`.

Pekepinnen sitter noen millimeter foran måleviseren, så les alltid av rett
forfra. Skrått fra siden gir parallaksefeil på et par hundre watt.

---

## Valgfri variant med to instrumenter

Vil du ha ekte bevegelse også for øyeblikkseffekten, henger du på et instrument
nummer to. Det projiserte time-snittet er tallet som avgjør regningen og beveger
seg rolig; øyeblikkseffekten rykker hver gang noe slår seg på, og det er halve
moroen. To visere på samme aksel er ikke en vei ut, for det krever et
differensialverk du ikke får kjøpt billig.

Andre instrumentet får samme behandling: eget par av fastmotstand og trimpot,
koblet til GPIO26 på klassisk ESP32 (GPIO18 på S2). Samme ESP32 driver begge.

I `esphome/effektvakt-panel.yaml` ligger begge halvdelene som kommenterte blokker,
en under `output:` og en under `sensor:`. Fjern kommentartegnene på begge, og
sett inn din egen power-sensor i `entity_id`. Merk at AMS-sensorer rapporterer i
watt, ikke kilowatt, og at lambdaen i den kommenterte blokken deler på 1000 av
den grunn. Rapporterer din sensor allerede kW, fjerner du divisjonen.

Begge instrumentene bruker samme `maks_kw`, altså samme skala, så de kan ha helt
like skiver og leses mot hverandre. Står den svarte langt over den røde, er det
noe som nettopp slo seg på og time-snittet har ikke tatt det inn ennå.

---

## Montering

Sitter instrumentet i sitt eget kabinett, er det plass til ESP32-en bak verket på
de fleste panelmetre. Har du bygget ny kasse, lag den dyp nok til at
USB-kontakten kommer til uten å brekke kabelen. Legg strømforsyningen utenfor
kassen.

Skru kassen på vegg der du faktisk ser den fra der du sitter. Poenget med et
analogt instrument er at du leser av det i forbifarten, uten å hente telefonen,
og et panel i gangen blir aldri sett på.

Wifi-dekning er verdt en tanke før du borer. ESP32-en har en liten antenne, og en
metallkasse gjør den ikke bedre. Sjekk signalstyrken på plassen før du fester
noe permanent.
