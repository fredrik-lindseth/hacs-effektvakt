# Nettselskap og tariffgrunnlag

`custom_components/effektvakt/dso.py` genereres fra [fri-nettleie](https://github.com/kraftsystemet/fri-nettleie), lisensiert CC-BY-4.0. Ikke rediger den for hånd.

## Formatet

`DSO_LIST` har stabile nøkler som ligger i brukernes oppsett. `scripts/dso_kilder.json` bestemmer nøkkel, navn, prisområde, kildefil og mva-sone. Kilden oppgir nedre kW-grense og kr/år uten mva; generatoren lager øvre kW-grense og kr/mnd med riktig mva. Ørene beholdes i tariffgrunnlaget.

Commit og tariffdato er pinnet i `_meta`. `--check` sammenligner derfor mot samme kilde helt til pinnen oppdateres.

## Oppdatere satsene

1. Oppdater `_meta.commit` og `_meta.tariff_dato` i `scripts/dso_kilder.json`.
2. Regenerer og les diffen.
3. Kjør prosjektets sjekker før commit av begge filene.

```bash
python3 scripts/generer_dso_fra_fri_nettleie.py
just test
```

Bruk `--kilde <sti>` for en lokal utsjekk; ellers lastes kilden ned. Nye nettselskap legges i kildetabellen, uten å endre eksisterende nøkler.

## Nettselskap som ikke følger NVE-modellen

69 av 71 selskaper bruker `TRE_DØGNMAX_MND`: snittet av tre høyeste timegjennomsnitt fra ulike dager. Følgende er sperret for operative råd:

| Nettselskap | Metode |
| --- | --- |
| `sor_aurdal_energi` | `MND_MAX`: høyeste enkelttime. |
| `tinfos` | `UKJENT`: tariffmetoden er ikke bekreftet. |

Metoder med amperegrenser eller uten kW-trinn tas ikke inn i tabellen.

## Egendefinert DSO

Velg **Egendefinert** og oppgi `[øvre kW-grense, kr/mnd]`-par, for eksempel `[[2, 155], [5, 250], [null, 415]]`. Metoden må være støttet topp-3; egne priser gir ikke støtte for en annen avregningsmetode.

Øverste trinn må ha `null` som grense; ellers utløses repair. Trinnene kan foreløpig bare settes ved oppretting. Å slette og opprette på nytt mister tidligere dagsmaks i oppsettet.

## Hva CI sjekker

```bash
just dso-hent
just dso-sjekk _fri-nettleie
```

CI kontrollerer generert tabell mot pinnet kilde. Tester vokter stabile nøkler, stigende terskler, ikke-synkende priser og åpent topptrinn. Se [utviklerguiden](development.md).

## Øvre kildegrense

Nettselskapets [privatprisliste](https://nettselskapet.as/strompris) avklarer ikke over 50–75 kW. Ved projisert topp-3 på eller over 75 kW blir risiko, kostnad og kuttråd ukjent. Etna har grense 25 kW. Egendefinerte tabeller har ingen kataloggrense.
