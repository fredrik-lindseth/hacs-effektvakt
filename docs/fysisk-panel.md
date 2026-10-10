# Fysisk panel

Skisse til et analogt panel som viser projisert timegjennomsnitt fra HA. [ESPHome-oppsettet](../esphome/effektvakt-panel.yaml) er validert med ESPHome 2026.5.1, men maskinvaren er ikke bygget eller prøvd. Motstandsverdiene må kontrolleres mot instrumentet.

## Hva originalen målte

Originalen målte strøm i én fase. Dette panelet bruker HA-sensoren over wifi og driver et DC-instrument. Alt er lavspenning; ingen tilkobling til strømnettet eller strømtransformator.

## Deleliste

| Del | Krav |
| --- | --- |
| Panelmeter | Dreispoleverk for DC, fullutslag høyst 1 mA. |
| ESP32 | Klassisk WROOM/WROVER eller S2 med DAC; ikke C3/C6/S3. |
| Seriemotstand og trim | For 1 mA-eksemplet: 2,2 kΩ fast, 1/4 W, og flerdreid 2 kΩ trimpot. |
| Strømforsyning | USB 5 V, 1 A. |
| Montering | Koblingsbrett, kabinett, stiv skiveplate og veggfeste. |
| Valgfri pekepinn | 0,3–0,5 mm svart styren/messing, M2-skrue og nylonskive. |

### Krav til instrumentet

Kontroller fullutslagsstrøm, spolemotstand, skivestørrelse, akselplassering og utslagsvinkel før bygging. Skiven er 100 × 100 mm, med navet 50 mm fra venstre og 90 mm fra toppen. Standard sveip er 100°; endre `VINKEL_SVEIP` i `faceplate.py` hvis instrumentet har et annet sveip.

## Kobling

```text
GPIO25 ──[ 2,2 kΩ ]──[ trim 2 kΩ ]──(+) instrument (−)── GND
```

Ved omtrent 3,3 V og 1 mA trengs omtrent 3,3 kΩ totalt, inkludert spolen. Andre fullutslagsstrømmer krever andre motstandsverdier. Koble aldri instrumentet direkte til pinnen. ESP32-S2 bruker GPIO17/GPIO18; endre `dac_pin` tilsvarende.

### Oppløsning og oppdatering

DAC har 256 trinn, omtrent 59 W per trinn på 15 kW-skala. HA oppdaterer hvert 15.–60. sekund.

## Programvare

```bash
cp esphome/secrets.example.yaml esphome/secrets.yaml
$EDITOR esphome/secrets.yaml
esphome config esphome/effektvakt-panel.yaml
esphome run esphome/effektvakt-panel.yaml
```

Legg enheten til som ESPHome-enhet i HA. Den har kalibreringsmodus, kalibreringsnivå og selvtest. Sett `maks_kw` lik trykt skalatopp. Ved mistet HA-forbindelse eller utilgjengelig sensor parkeres viseren på null innen 30 sekunder.

## Kalibrering

1. Sett trimpotten til maksimal motstand før første oppstart.
2. Slå på kalibreringsmodus, velg 0 % og still mekanisk nullpunkt.
3. Velg 100 % og trim til siste skalamerke.
4. Kontroller 0 % igjen og deretter 50 % midt på skalaen.
5. Slå av kalibreringsmodus og sammenlign med HA-sensoren.

### Kryss mot en kjent verdi

Konstant avvik tyder på nullpunkt; avvik som vokser med utslaget tyder på fullskala. Feil midtverdi kan skyldes skiveplassering eller aksel. Hvis fullutslag ikke nås, kontroller seriemotstanden; ved for stort utslag kan `dac_maks` reduseres etter trim.

## Skiven

```bash
python3 scripts/export_faceplate.py --liste
python3 scripts/export_faceplate.py --dso bkk --out geha-bkk.svg
python3 scripts/export_faceplate.py --dso bkk --png
```

Bruk standardvarianten `print`. Oppgitt `--maks-kw` rundes opp til lesbar skalatopp; bruk den ferdige verdien også i ESPHome.

### Fra SVG til plate

Sett fysisk størrelse ved import/utskrift: viewBox `0 0 1000 1000` tilsvarer 100 × 100 mm. Konverter tekst til baner før trykk eller gravering. Bruk matt overflate, stiv plate og akselhull på riktig sted. [Eksportdetaljer](development.md#eksportere-geha-meter-skiven).

## Den svarte viseren

Den fysiske svarte viseren er en manuell grensemarkør, ikke en måleviser. Fest pekepinnen med friksjon over akselen og sett den til ønsket trinngrense. Les rett forfra for å unngå parallakse. Dashboard-kortets svarte viser viser derimot momentan effekt.

## Valgfri variant med to instrumenter

Et annet instrument kan vise momentan effekt via GPIO26 (GPIO18 på S2), med egen motstand og trim. Aktiver begge kommenterte blokker under `output:` og `sensor:` i ESPHome-filen. Sett egen effektsensor; fjern divisjonen på 1 000 hvis sensoren allerede viser kW. Begge instrumenter bruker samme `maks_kw`.

## Montering

Kontroller wifi-dekning, plass til USB-kabel og mekanisk klaring. Hold strømforsyningen utenfor kassen. Panelet skal ikke kobles til strømnettet eller en strømtransformator.
