# Release-noter

Leseren har allerede installert integrasjonen. Beskriv endringene fra forrige versjon og bare handlingene som er nødvendige for oppgraderingen. Installasjon, dashbordoppsett og valgfrie blueprints står i README. Skriv hele avsnitt og listepunkter på én linje uten manuell linjebryting. Bruk vanlige ord og konkrete endringer. Sjekk tidligere manifestversjoner i git før du kaller en release den første.

GitHub-release-bodyen vises i HACS inne i Home Assistant. Første release beskriver hva brukeren får. Senere releaser beskriver funksjoner og synlige rettelser siden forrige versjon. Lengden følger endringene.

Kilden er den daterte versjonsseksjonen i `CHANGELOG.md`. Merk bare brukerrelevante punkter med `<!--kort-->`. Nødvendige handlinger står under `### Dette må du gjøre selv` og løftes først. Testtall, CI, refaktorering og datakildepinner hører hjemme i full CHANGELOG eller utviklerdokumentasjonen.

Release-bodyen er den korte noten med lenke til full endringslogg. Commit-logg, SHA-er og byggedetaljer fyller ikke denne teksten. Release-porten verifiserer fortsatt tagg, ZIP og attestasjon; se [SECURITY.md](../SECURITY.md).

Før publisering:

```bash
just release-note 0.4.0
just release-plan
```

Les selve noten slik en bruker møter den i oppdateringsdialogen. Hvert punkt skal si hva brukeren får, merker eller må gjøre. En kort overskrift med et langt teknisk avsnitt er fortsatt en lang note.

Push til `main` kjører CI for den konkrete commiten. Først når testene, HA-versjonsmatrisen, dekning, kvalitet, HACS og hassfest er grønne, kan den daterte versjonen publiseres. Udaterte versjoner blir stående under arbeid.

Etter publisering:

```bash
just release-verify v0.4.0
```
