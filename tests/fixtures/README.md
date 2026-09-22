# Replay-fixturer

Timesforbruk fra et ekte BKK-anlegg i NO5, brukt av `tests/test_coordinator_replay.py`
til å spille av hele måneder mot terskelmodellen.

Frem til september 2026 lå dette som en symlink til `hacs-strømkalkulator`, så testene
ble stille skippet i alle klonene som ikke hadde søskenrepoet ved siden av, altså i CI.
Nå ligger dataene her.

## Filene

`bkk_<måned>_<år>_hourly.json`, én fil per måned, med `metadata` og `hours`.
Hver time har `start_local` (lokal tid med offset), `kwh`, `spot_nok_kwh_eks_mva`
og `p_max_w`. Replay-testen bruker `start_local` og `kwh`; resten er med fordi det
allerede var målt, og fordi kWh alene ikke skiller en jevn time fra en med en topp.

Timetallet per måned følger kalenderen: februar 672, mars 743 (sommertid 29.03),
måneder med 30 dager 720, resten 744.

## Opphav

Eksportert fra Home Assistants recorder i `hacs-strømkalkulator`, der de samme
filene verifiserer BKK-fakturaer time for time mot Elhub. Kopiert derfra
2026-09-22 med timesdataene ordrett. Metadata er trimmet: entity-IDene og
målerstandene i originalen sier hvor anlegget står, og det trengs ikke her.

Skal de oppdateres, hentes en ny måned fra
`hacs-strømkalkulator/tests/fixtures/` og trimmes på samme måte.
