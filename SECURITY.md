# Sikkerhet og verifisering

## Verifiser en release

Hver release har en [artifact attestation](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds) som kryptografisk binder ZIP-filen til kildekoden og til workflow-kjøringen som bygde den.

`effektvakt.zip` er ikke bare et vedlegg på release-siden: `zip_release` står i `hacs.json`, så det er nøyaktig den filen HACS laster ned og pakker ut i `custom_components/effektvakt/` hos deg. Attestasjonen dekker dermed det som faktisk blir installert, inkludert Lovelace-kortet under `www/` og ikonene under `brand/`.

### Hvorfor

En custom integrasjon i Home Assistant kjører med full tilgang til systemet ditt. Du bør kunne slå fast at koden du installerer er den samme koden du kan lese på GitHub, uten å måtte stole på hverken oss eller GitHub på ordet.

### Med GitHub CLI

1. Last ned `effektvakt.zip` fra [siste release](https://github.com/fredrik-lindseth/hacs-effektvakt/releases/latest).

2. Verifiser attestasjonen:

   ```bash
   gh attestation verify effektvakt.zip --repo fredrik-lindseth/hacs-effektvakt
   ```

3. Svaret skal begynne med:

   ```text
   ✓ Verification succeeded!
   ```

   Resten av utskriften sier hvilken commit og hvilken workflow som bygde filen.

### Sammenlign sha256

Release-noten har sha256-en til ZIP-en og commiten den er bygget fra. Sjekk at filen du lastet ned er den samme:

```bash
sha256sum effektvakt.zip
```

### Bygg ZIP-en selv

Bygget er deterministisk. ZIP-en pakkes fra git-objektene på commiten taggen peker på, med fast tidsstempel og rettigheter fra git, så to bygg av samme commit gir bit-identiske filer uansett maskin, klokke og umask. Da kan du bygge den samme filen selv og sammenligne:

```bash
git clone https://github.com/fredrik-lindseth/hacs-effektvakt
cd hacs-effektvakt
python3 scripts/release_publish.py build --sha vX.Y.Z --output /tmp/effektvakt.zip
```

Utskriften er sha256-en, og den skal være identisk med den i release-noten og med den du lastet ned.

Vil du sjekke hele kjeden i ett kall, altså at tagg, ZIP og attestasjon peker på samme artefakt:

```bash
just release-verify vX.Y.Z
```

Den feller med exit 2 hvis de ikke gjør det.

### Hva flyten garanterer

Kandidaten er ett ledd: repo, full commit-SHA og manifestversjon. Alle tre bindes til den samme commiten.

- ZIP-en bygges fra git-objektene på kandidat-SHA-en, aldri fra arbeidstreet på runneren, så innholdet _er_ det taggen peker på.
- Taggen opprettes eksplisitt på den SHA-en, og den flyttes aldri. Finnes den fra før, derefereres den og sammenlignes.
- Attestasjonen verifiseres mot repo, kilde-SHA, signer-workflow og sha256-en til ZIP-en før noe blir offentlig.
- Kandidaten må ligge på hovedgrenen, så det som går ut til brukerne kan ikke komme fra en gren som aldri har vært på `main`.
- Alt skjer i en draft, og `draft=false` er siste kall. Feiler noe før det, finnes det ingen halv release å rydde, og et nytt forsøk på samme commit plukker opp der det stoppet.

## Rapporter et sikkerhetsproblem

Opprett et issue på [GitHub](https://github.com/fredrik-lindseth/hacs-effektvakt/issues), eller ta kontakt direkte hvis det ikke bør stå offentlig.
