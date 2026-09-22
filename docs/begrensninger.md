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

## De første dagene av måneden er vakten for streng

Måltrinnet, altså det Effektvakt forsvarer, er det billigste trinnet måneden fortsatt kan ende på. Tidlig i måneden er to eller tre av topp-3-plassene tomme, og da er det billigste mulige trinnet det laveste i tabellen. På BKK betyr det at vakten de første dagene måler mot 2 kW-trinnet til 155 kr, og melder `over_terskel` for timer et vanlig hus ikke kan unngå.

Det er ikke feil regnet. Holder du hver eneste dag under 2 kW, betaler du faktisk 155 og ikke 250. Men det er sjelden et valg noen tar, og fram til dagene som er låst inn løfter skranken opp i det trinnet husstanden faktisk lander på, er varselet strengere enn det er nyttig.

To ting demper det. `kostnad_denne_timen_kr` er 0 i nettopp disse timene, for måneden er der uansett, og varsel-blueprintet leser den. Og timetaket er `max(dagens maks, dagstaket)`, så varselet slår bare ut på timer som setter ny dagsrekord, ikke hele dagen.

Mest treffsikkert ville vært å la forrige måneds oppgjorte topp-3 være gulv for måltrinnet de første dagene. Det er ikke gjort, og `_previous_month_top_3_snitt_kw` ligger alt lagret hvis noen vil.

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
