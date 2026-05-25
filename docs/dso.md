# DSO-data

## Innhold

`custom_components/effektvakt/dso.py` inneholder kapasitetstrinn og priser for 72 norske nettselskap. Filen er auto-generert fra `hacs-strømkalkulator/custom_components/stromkalkulator/dso.py` og skal ikke redigeres manuelt.

Hver DSO har:

```python
{
    "navn": "BKK",
    "prisomrade": "NO5",
    "kapasitetstrinn": [
        (2.0, 230),    # (kW-terskel, kr/mnd)
        (5.0, 415),
        (10.0, 600),
        (15.0, 800),
        (20.0, 1000),
        (25.0, 1200),
        (float("inf"), 1600),
    ],
}
```

Trinnlisten er sortert stigende på kW-terskel. Siste element har `float("inf")` som terskel og representerer det øverste trinnet uten øvre grense.

---

## NVE-modellen

Alle DSO-ene i lista bruker NVE-modellen: kapasitetsleddet bestemmes av snittet av de tre høyeste time-forbrukene fra ulike dager i måneden. Selve trinn-strukturen (antall trinn og priser) varierer mellom DSO-er.

---

## Oppdatering

Kapasitetstrinn og priser endres typisk en gang i året, ved nyttår. For å synkronisere:

```bash
python scripts/sync_dso_from_stromkalkulator.py
```

Scriptet leser `../hacs-strømkalkulator/custom_components/stromkalkulator/dso.py`, trekker ut kapasitetstrinn-data og skriver ny `dso.py`. CI-sjekk i `tests/test_dso_data.py` verifiserer strukturen etter generering.

---

## Egendefinert DSO

Velger du **Egendefinert** i config flow, kan du legge inn trinnene manuelt. Formatet er en liste med par: `[[2.0, 230], [5.0, 415], ...]`. Disse lagres i `entry.data["kapasitetstrinn_custom"]` og overskriver DSO-oppslaget.

Egendefinert konfigurasjon er nyttig hvis:

- Nettselskapet ditt ikke er i lista
- Nettselskapet ditt bruker andre trinn enn det vi har registrert
- Du vil teste med avvikende trinn

---

## CI-sjekk for drift

`tests/test_dso_data.py` validerer at:

- Alle kapasitetstrinn-lister er sortert stigende
- Alle kW-terskler er positive (unntatt siste `inf`)
- Alle priser er positive heltall
- Minst 70 DSO-er er lastet (sanity-check mot utilsiktet sletting)

Hvis DSO-data drifter fra strømkalkulator uten at synk-scriptet har kjørt, feiler CI.
