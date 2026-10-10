# Sparepotensial og lastprofiler

## Regnestykket fra BKK

Månedens historiske topp-3-snitt var 5,823 kW i desember 2025 og 5,702 kW i februar 2026. Med 415 kr per måned over 5 kW og 250 kr på eller under 5 kW gir 1 kW reduksjon snittene 4,823 og 4,702 kW og 165 kr spart i hver måned: til sammen 330 kr. 600 W reduksjon gir 5,223 og 5,102 kW, fortsatt i samme trinn. Timesdataene er beskrevet i [fixtur-dokumentasjonen](../tests/fixtures/README.md).

## Hva kan det bli på et år?

Syntetisk BKK-eksempel: fem måneder i 5–10 kW-trinnet og sju i 2–5 kW. Årlig kapasitetsledd: `5 × 415 + 7 × 250 = 3 825 kr/år`.

| Måneder flyttet til billigere trinn | Spart per år | Andel av kapasitetsleddet |
| ---: | ---: | ---: |
| 2 | 330 kr | 8,6 % |
| 4 | 660 kr | 17,3 % |
| 5 | 825 kr | 21,6 % |

Med 16 000 kWh/år, halvparten i hver tariffperiode, Norgespris på 50 øre/kWh og BKKs 2026-energiledd blir kraft og nettleie omtrent 17 379 kr/år før leverandørpåslag og fastbeløp: `8 000 + 8 000 × (0,4613 + 0,2329) + 3 825`. Da tilsvarer 330–660 kr omtrent 1,9–3,8 % av denne kostnaden. Regnestykket forutsetter forbruk innen Norgespris-taket hver måned og uendret fordeling mellom tariffperiodene.

Gevinsten krever lavere fakturerte trinn uten nye topper ved gjeninnkobling. Ganging med tolv passer bare ved tolv ellers dyrere måneder; sparingen kan også bli null. [BKK-satser](https://www.bkk.no/en/grid-tariffs-for-private-customers).

Elbil, solceller og komfortkrav er omtalt i [FAQ](faq.md#hvor-mye-sparer-jeg-egentlig-på-dette); se også [tidsflytting](scenario-nattvask.md) og [prisordninger](scenario-norgespris.md).

## Et mål for måneden

I utviklingsversjonen velger du **Mål for måneden** under **Konfigurer**, for eksempel 5 kW. Målet forsvares fra første dag og kan gi tidligere og flere kutt, også før timen låser inn dyrere nettleie. **Av** bruker standardvurderingen.

Når låste døgnmaks gir et minste mulig topp-3-snitt over målet, får det status `tapt` og vanlig vurdering overtar. Valget beholdes til neste måned. `maal_kutt_anbefalt` beskriver bidraget til målet; kostnadsattributtene beskriver fortsatt tariffvirkningen nå. Se [sensorene](sensorer.md#valgt-månedsmål) og behold blueprintenes tidsgrenser.

## Hva et lastkutt kan bidra med

600 W gjennom en time bidrar med 0,6 kWh; i ti minutter er bidraget 0,1 kWh. Varigheten og gjenoppvarmingen avgjør virkningen på timegjennomsnittet. [Lastprofiler](lastprofiler.md) forklarer målt effekt, arbeidssyklus, restvarighet og bruk i HA.

## Regneeksempel og simulert styring

Historisk reduksjon av toppene er et ideelt regneeksempel. `scripts/simuler_sparing.py` prøver styring underveis uten framtidskunnskap. Timesforbruk behandles som jevn effekt; en tenkt fleksibel last utsettes og energien føres tilbake etter valgt effekt, maks utkobling og minste påtid. Modellen beskriver tidsflytting, ikke temperatur eller målt sparing.

Med 600 W og 1 kW, både vanlig vurdering og et valgt mål på 5 kW, ga denne modellen ingen reduksjon i kapasitetsleddet over de komplette månedene i datagrunnlaget når utsatt energi ble ført tilbake straks med samme effekt. I noen måneder økte topp-3-snittet uten å endre trinnet. Januar 2026 har 105 manglende timer og holdes utenfor samlet sammenligning. Resultatet viser hvorfor gjeninnkoblingen og plasseringen av forbruket senere er like viktig som selve kuttet. Det fastslår ikke at reell styring er uten nytte.

Kjør analysene fra repo-roten:

```bash
uv run --group unit python scripts/simuler_sparing.py
uv run --group unit python scripts/analyser_lastprofil.py profil.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --terskel-w 100
```

Bruk lokale måledata. Reell sparing må dokumenteres med tilgjengelige laster i topptimene, faktisk kutt, gjeninnkobling og forbruk etterpå. [Lastprofiler](lastprofiler.md) og [eksempelrapport](research/lastprofil-rapport.md).
