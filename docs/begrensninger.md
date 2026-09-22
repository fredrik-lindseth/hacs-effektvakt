# Begrensninger

Kjente begrensninger. Noen er designvalg, andre er ting som kan forbedres.

---

## 60-sekunders tick i lav-risiko-modus

Ved `god_margin` og `naermer_seg_terskel` oppdateres sensorer hvert 60 sekund. Et effekthopp kl. 18:58 (to minutter før time-slutt) vil først bli fanget opp ved neste tick, som kan komme like etter time-slutt. Da er det for sent å handle.

Mitigering: Tick-frekvensen øker til 30s ved `like_under_terskel` og 15s ved `over_terskel`. Problemet oppstår når forbruket hopper direkte fra rolig til over grensen uten å passere `like_under_terskel` først. I praksis er dette sjeldent, men det skjer.

---

## Blind-strategi: duty cycle-problem

Med `blind`-strategi antar Effektvakt 0,3 kW tilgjengelig kutt. Dette er gjennomsnittet over tid, ikke øyeblikksverdi. I praksis:

- 85% av tiden: VVB er allerede av, kuttet gir 0 kW
- 15% av tiden: VVB varmer, kuttet gir 2 kW

Replay-tester på BKK-måneder viser at `blind`-strategi gir meningsfull forbedring i bare 2 av 5 måneder med VVB-shed alene. De tre månedene der det ikke hjelper er måneder der VVB tilfeldigvis ikke varmer i de kritiske minutt-vinduene.

Løsning: Bruk `vvb_status`-strategi med en smart plugg på VVB.

---

## Topp-3-snitt trenger 2+ dager

`effective_threshold_kw` faller tilbake til `next_tier_threshold_kw` de to første dagene av måneden (færre enn 2 dager logget). Marginen vises dermed uten topp-3-justering den første dagen, noe som gir et optimistisk bilde.

Fra dag 2 tar Effektvakt hensyn til topp-2-snittet. Fra dag 4 (når alle tre topp-dagene kan være satt) er beregningen fullstendig. Dette er riktig oppførsel, men kan overraske hvis du starter overvåkingen sent i måneden.

---

## DSO-data er statisk

`dso.py` er auto-generert fra [fri-nettleie](https://github.com/kraftsystemet/fri-nettleie) og oppdateres via `scripts/generer_dso_fra_fri_nettleie.py`. Prisene for kapasitetstrinn endres typisk en gang i året (nyttår). Mellom oppdateringer kan Effektvakt bruke utdaterte trinnpriser.

Bruker du `Egendefinert` DSO i config, er du ansvarlig for å holde trinnene oppdatert selv.

---

## HA-restart mister hysterese-pending-state

Coordinatoren persisterer `hysterese_state.nivå` til disk, men ikke `pending_nivå` og `pending_since`. Etter HA-restart er det aktive risiko-nivået korrekt, men eventuelle ventende trinnendringer mistes. Timeren for nedgang i risiko starter på nytt.

Konsekvens: Etter restart kan risiko holde seg på `like_under_terskel` litt lenger enn forventet, selv om forbruket har gått ned. Det er det konservative valget.

---

## Energy-sensor mangler: dårligere nøyaktighet tidlig i timen

Uten energy-sensor estimeres `actual_kwh_this_hour` fra effekt _ tid. De første par minuttene av en time er estimatet basert på svært lite akkumulert data, og `projected_avg` domineres av `current_kw _ remaining_h`. Projeksjon i starten av timen er altså mer sensitiv for kortvarige effektspisser.

Med energy-sensor kompenseres dette ved at delta leses direkte fra telleren.

---

## Ingen historikk mellom instanser

Effektvakt lagrer data per `entry_id`. Hvis du sletter og gjenoppretter integrasjonen, mister du månedenes `daily_max_kw`. Topp-3-snittet starter på nytt. Dette er ønsket atferd for å unngå datakontaminering mellom instanser, men betyr at reinstallasjon midt i måneden gir ufullstendig bilde resten av måneden.
