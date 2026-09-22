## Beskrivelse

<!-- Hva endrer denne PR-en, og hvorfor -->

## Type endring

- [ ] Bugfix
- [ ] Ny funksjonalitet
- [ ] Refaktorering
- [ ] Dokumentasjon
- [ ] Brytende endring

## Relaterte issues

<!-- Lukk issues med "Closes #123" -->

## Sjekkliste

- [ ] Koden følger stilen i repoet, og norsk i kode, kommentarer og dokumentasjon
- [ ] Tester er skrevet eller oppdatert
- [ ] `pytest tests/` passerer
- [ ] `ruff check` passerer
- [ ] `pre-commit run --files <filene dine>` passerer
- [ ] Dokumentasjonen i `docs/` er oppdatert der endringen merkes
- [ ] Jeg har lest gjennom min egen diff

## Rører endringen noe av dette?

- [ ] `dso.py` (den er autogenerert, se `AGENTS.md`)
- [ ] Entitets-id-er eller `unique_id` (brukeren mister historikk)
- [ ] Hysterese eller failsafe i blueprintene (last kan bli stående av)
