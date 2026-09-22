# DSO-data

## Innhold

`custom_components/effektvakt/dso.py` har kapasitetstrinn og priser for 71 norske
nettselskap. Filen er generert og skal ikke redigeres for hånd.

Hver DSO ser slik ut:

```python
"bkk": {
    "navn": "BKK",
    "prisomrade": "NO5",
    "kapasitetstrinn": [
        (2.0, 155),  # (øvre kW-grense, kr/mnd inkl. mva)
        (5.0, 250),
        (10.0, 415),
        (15.0, 600),
        ...
        (float("inf"), 6900),
    ],
},
```

Trinnlisten er sortert stigende på kW-terskel, og terskelen er øvre grense for
trinnet. Siste element har `float("inf")` og er det øverste trinnet.

---

## Hvor tallene kommer fra

Satsene hentes fra [kraftsystemet/fri-nettleie](https://github.com/kraftsystemet/fri-nettleie),
en dugnadsbasert samling av norske nettleie-tariffer i YAML, lisensiert
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Det er samme kilde
hacs-strømkalkulator validerer sine egne satser mot, så vi går rett til den i
stedet for å kopiere fra et annet repo på disk.

Nøklene (`bkk`, `tensio_tn` og resten) ligger i brukernes config entries og kan
ikke endres. Derfor er det `scripts/dso_kilder.json` som bestemmer hvilke
nettselskap som finnes. Der står nøkkel, visningsnavn, prisområde, hvilken
fri-nettleie-fil satsene hentes fra, og om husholdninger i området har
mva-fritak (Nord-Norge og tiltakssonen har det). Generatoren henter bare prisene.

fri-nettleie oppgir nedre kW-grense og kr/år eks. mva. Vi lagrer øvre kW-grense
og kr/mnd inkl. mva, så øvre grense for et trinn er nedre grense for det neste,
og prisen deles på 12 og ganges med mva-faktoren. Halve kroner rundes opp, slik
prislistene selv gjør.

Kjøringen er pinnet til en commit og en tariff-dato i `_meta` i
`scripts/dso_kilder.json`. Da gir `--check` samme svar neste år som i dag,
og tabellen endrer seg bare når et menneske flytter pinnen.

---

## Oppdatere satsene

Nettleien endres typisk ved nyttår, og ellers når et nettselskap legger om.

1. Finn ny commit i fri-nettleie og sett `_meta.commit` og `_meta.tariff_dato`
   i `scripts/dso_kilder.json`.
2. `python3 scripts/generer_dso_fra_fri_nettleie.py`
3. Les gjennom diffen i `dso.py`, kjør `python3 -m pytest tests/test_dso_data.py`,
   og commit begge filene.

Scriptet laster ned tariffene fra den pinnede commiten. Har du en utsjekk
liggende, gir `--kilde ~/src/fri-nettleie` samme resultat uten nett. CI bruker
den varianten, med en `actions/checkout` av commiten fra `_meta`.

Kommer det et nytt nettselskap, legges det inn som en rad i
`scripts/dso_kilder.json`. Scriptet sier fra om hvilke filer i fri-nettleie som
ikke er dekket av tabellen.

---

## Nettselskap som ikke følger NVE-modellen

Effektvakt regner etter NVE-modellen: kapasitetsleddet bestemmes av snittet av
de tre høyeste timene fra ulike dager i måneden. fri-nettleie kaller den
`TRE_DØGNMAX_MND`, og 69 av de 71 bruker den.

To gjør det ikke, og for dem er trinnprisene riktige mens *hvilket* trinn du
havner på regnes ut på en annen måte:

| Nettselskap         | Metode    | Betyr                                      |
| ------------------- | --------- | ------------------------------------------ |
| `sor_aurdal_energi` | `MND_MAX` | Høyeste enkelttime i måneden, ikke snitt av tre |
| `tinfos`            | `UKJENT`  | Verken tinfos.no eller fri-nettleie sier hvilken kW-verdi trinnet slås opp med |

Generatoren lister dem ved hver kjøring. Metoder som ikke er kW-trinn i det hele
tatt (`OV_TREFASE` med ampere på tersklene, `FEM_VEKTET_ÅR` uten trinn) tas ikke
inn i tabellen; ingen av nettselskapene våre bruker dem i dag.

---

## Egendefinert DSO

Velger du **Egendefinert** i config flow, legger du inn trinnene selv. Formatet
er en liste med par: `[[2.0, 230], [5.0, 415], ...]`. De lagres i
`entry.data["kapasitetstrinn_custom"]` og overstyrer oppslaget i `dso.py`.

Det er nyttig hvis nettselskapet ditt mangler i lista, bruker andre trinn enn vi
har registrert, eller du vil teste med avvikende trinn.

---

## Hva CI sjekker

`scripts/generer_dso_fra_fri_nettleie.py --check` kjøres i CI og som
pre-commit-hook når `dso.py`, generatoren eller kildetabellen endres. Den feller
bygget hvis `dso.py` ikke er nøyaktig det generatoren ville skrevet fra den
pinnede commiten, altså ved håndredigering eller ved at noen har flyttet pinnen
uten å regenerere.

`tests/test_dso_data.py` sjekker i tillegg at

- ingen nøkkel som ligger i en config entry har forsvunnet
- `dso.py` og `scripts/dso_kilder.json` har samme nøkler
- tersklene er stigende og prisene ikke synker
- øverste trinn er `inf`, ikke et tak som 999 kW
- BKK står med 155, 250 og 415 kr for 2, 5 og 10 kW, som er den ene tabellen vi
  har kontrollert mot faktura
