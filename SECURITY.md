# Sikkerhet og verifisering

## Verifiser en release

HACS installerer `effektvakt.zip` fra releasen. En artifact-attestasjon binder ZIP-en til repo, kildecommit og workflow. Last ned filen fra [siste release](https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest) og kontroller med GitHub CLI:

```bash
gh attestation verify effektvakt.zip --repo fredrik-lindseth/hacs-effektvakt
```

Svaret skal si `Verification succeeded!`. Se [GitHubs veiledning](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds) for detaljene.

### Bygg ZIP-en selv

ZIP-en bygges deterministisk fra taggens git-objekter, med faste tidsstempler og rettigheter:

```bash
python3 scripts/release_publish.py build --sha vX.Y.Z --output /tmp/effektvakt.zip
```

Kjør fra repoet og sammenlign utskriftens SHA-256 med filen du lastet ned (`sha256sum effektvakt.zip`). Hele kjeden kan kontrolleres med:

```bash
just release-verify vX.Y.Z
```

### Hva flyten garanterer

Repo, full SHA og manifestversjon identifiserer kandidaten. Tagg, ZIP og attestasjon må peke på samme commit. Taggen flyttes ikke, og kandidaten må ligge på `main`. Publisering skjer først etter validering; feil etterlater en draft som kan gjenopptas på samme commit. Se [releaseflyten](docs/release-notes.md).

## Rapporter et sikkerhetsproblem

Opprett et [GitHub-issue](https://github.com/fredrik-lindseth/hacs-effektvakt/issues), eller ta kontakt direkte hvis opplysningene ikke bør deles offentlig.
