# Endringslogg

Alt som merkes av den som bruker Effektvakt, står her. Formatet er
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), og versjonene følger
[SemVer](https://semver.org/).

Punktene som er merket `<!--kort-->` er de som havner i den korte
release-noten, altså teksten HACS viser i oppdateringspanelet inne i Home
Assistant. Resten står bare her. Overskriften får utgivelsesdatoen sin den
dagen versjonen faktisk går ut; fram til da sier den «Ikke sluppet», og
release-flyten nekter å slippe en versjon uten dato.

## [0.4.0] - Ikke sluppet

Første release. Ingenting har vært ute før denne, så listen under er hva du
får, ikke hva som er endret siden sist. Har du kjørt integrasjonen fra `main`
underveis, er det «Fikset» som gjelder deg.

### Dette må du gjøre selv

- Velg nettselskap og pek på effektsensoren din under **Innstillinger >
  Enheter og tjenester > Legg til integrasjon > Effektvakt**. Resten har
  standardverdier som duger. Stegene står i [docs/oppsett.md](docs/oppsett.md).
- Kortet legges inn i dashbordet selv. Det registrerer seg som ressurs ved
  oppstart, men Home Assistant setter ikke inn kort for deg.
  [docs/dashboard-kort.md](docs/dashboard-kort.md) viser oppsettet, og
  [docs/dashboard-eksempel.yaml](docs/dashboard-eksempel.yaml) kan limes rett
  inn.
- Blueprintene importeres for hånd hvis du vil at noe skal kuttes automatisk.
  Fire av dem, med import-lenker i [docs/blueprints.md](docs/blueprints.md).
  Uten dem varsler Effektvakt, men rører ingenting.

### Lagt til

- **Effektvakt sier fra før timen låser inn et dyrere kapasitetstrinn.**
  Seks sensorer: projisert time-snitt, margin til neste trinn, topp-3-snitt
  for måneden, risikonivå, tilgjengelig kutt og hva timen koster. Pluss
  `binary_sensor.effektvakt_kutt_ned_anbefalt`, som automasjoner trigger på, og
  `switch.effektvakt_automatikk` som hovedbryter. Alle sammen i
  [docs/sensorer.md](docs/sensorer.md). <!--kort-->
- **Et Lovelace-kort som gjenskaper den analoge effektvakten fra
  sikringsskapet.** Skiven tegnes av dine egne kapasitetstrinn, så
  kronebeløpene på buen er prisene nettselskapet ditt faktisk tar. Rød viser er
  projeksjonen, den tynne svarte er effekten akkurat nå, og trekanten utenfor
  buen er månedens topp-3-snitt. Kortet følger med integrasjonen og serveres
  derfra, det skal ikke installeres for seg. <!--kort-->
- **Kapasitetstrinn for 71 norske nettselskap**, hentet rett fra
  [fri-nettleie](https://github.com/kraftsystemet/fri-nettleie) på en pinnet
  commit og en pinnet tariffdato. Tabellen kan etterprøves mot kilden med én
  kommando, og CI feller hvis den har drevet. Har du et selskap som ikke står i
  listen, kan du skrive trinnene selv. [docs/dso.md](docs/dso.md). <!--kort-->
- **Fire blueprints** for varmtvannsbereder, panelovner, en generell last og
  ren varsling. Hver av dem slipper lasten ved neste timeskifte uansett hva
  Effektvakt sier, fordi verdien av et kutt slutter der.
  [docs/blueprints.md](docs/blueprints.md).
- **Svar på hva timen faktisk tåler.** Alle sensorene bærer
  `minutter_igjen_av_timen` og `kan_legge_paa_resten_av_timen_kw`: med ett kW
  margin klokka 18:50 er svaret 6 kW, ikke 1 kW, fordi en last som står i ti av
  seksti minutter bare flytter snittet med en sjettedel av effekten sin.
  Topp-3-sensoren sier hvilke tre dager snittet består av, om dagen i dag alt
  teller med, og hvilken dag en høyere time ville skjøvet ut.
- **Watchdog.** Henger coordinatoren i mer enn to minutter, settes sensorene
  til `unknown` framfor å stå igjen med gamle tall. Automasjoner kan skille
  «vet ikke» fra «alt er fint».
- **Reparasjonssaker når trinn-tabellen ikke er hel.** Peker oppsettet ditt på
  et nettselskap som er fjernet fra kilden, eller mangler egendefinerte trinn
  et åpent øverste trinn, får du beskjed framfor en sensor som stille sier «god
  margin» for alltid.
- **Diagnostikk** kan lastes ned fra integrasjonssiden og legges ved en
  feilrapport som den er. Den inneholder ikke hvilke sensorer du har pekt på.

### Fikset

Tre feil i kjernen, alle av typen som gjør vakten taus akkurat når den trengs.
De gjelder deg hvis du har kjørt integrasjonen fra `main`.

- **Terskelen gikk rett vei, men regnestykket gikk feil vei.** Effektvakt
  regnet med at jo høyere de andre dagene i måneden var, jo mer tålte dagen i
  dag. Topp-3-regelen sier det motsatte. Mot BKKs 5 kW-trinn meldte den
  gamle modellen 5,90 kW der grensen var 3,20, og 5,50 der den var 4,00: god
  margin, mens du var langt over. Hele terskelaritmetikken ligger nå ett sted,
  og margin, risiko, kostnad og «kan legge på» regner alle fra det samme taket.
  [docs/beregninger.md](docs/beregninger.md). <!--kort-->
- **Timen sto på 0,000 kWh med en vanlig norsk HAN-avleser.** Forbruket ble
  bygget utelukkende av differanser på energisensoren, og en HAN-avleser
  rapporterer én gang i timen. Projeksjonen kollapset dermed mot
  øyeblikkseffekten nettopp mens timen ble låst inn. Timen bygges nå opp av
  effektsensoren mellom hver avlesning, og energimåleren retter den etterpå,
  uten at de to legges oppå hverandre. kWh som kommer etter timeskiftet havner
  på timen før, og en oppstart midt i timen sier hvilket minutt vi har
  sammenhengende måling fra framfor å gjette. <!--kort-->
- **En vannkoker tidlig i timen kuttet varmtvannsberederen.** To minutter
  inn i timen er projeksjonen nesten bare øyeblikkseffekt, så 2 kW
  oppå 3,5 kW grunnlast ble til «over terskelen» selv om timen endte på 3,6.
  Kriteriet er nå kroner og ikke geometri: de to øverste risikonivåene krever
  at timen faktisk koster noe, regnet med fradrag for hvor mye en kortvarig
  last rekker å bety i det som er igjen av timen. <!--kort-->
- **Configure-dialogen slettet det du hadde lagret.** En tur innom for å
  justere sikkerhetsmarginen nullet ekstra effektsensorer og
  varmtvannssensoren, fordi skjemaet ble bygget med tomme standardverdier.
  Dialogen viser og beholder nå det som står lagret, og på Home Assistant 2025.12
  og nyere åpnet den seg ikke i det hele tatt.
- **Kuttet varte tvers over timeskiftet.** Blueprintene slapp lasten etter
  `max_off_minutes`, typisk 30 minutter, så et kutt fra 18:50 ga ti minutter
  nytte og tjue minutter som flyttet oppvarmingen inn i neste time og dro den
  opp. Kuttet venter nå på neste hele time, og `max_off_minutes` er blitt
  nødbremsen for tilfellet der timeskiftet aldri kommer.
- **Kortet ga «Fikk ikke hentet skiven» etter omstart** og ble stående slik til
  noen lastet siden på nytt for hånd. Det prøver nå igjen med voksende pause.
  Samtidig skiller kortet mellom en sensor som er borte og en integrasjon som
  ennå ikke har målt noe: 0,00 kW er et hus som ikke bruker strøm, og skal ikke
  stå der vi ikke vet.
- **Tjenestene virket bare på det siste oppsettet.** `set_safety_buffer` og
  `reset_topp_3` ble registrert per oppsett med hver sin lukking, så to
  oppsett overstyrte hverandre. De registreres nå én gang og virker på alle.

### Endret

- **Kuttkriteriet er kroner, ikke geometri.** Risikonivåene `over_terskel` og
  `like_under_terskel` krever nå at timen faktisk flytter kapasitetstrinnet.
  `like_under_terskel` kan derfor ikke lenger oppstå som rått nivå; den lever
  videre fordi hysteresen går innom den på vei ned.
- **Fellesattributtene på sensorene er navngitt om** slik at det står i
  klartekst hva marginen måles mot: `maal_terskel_kw`, `maal_trinn_kr`,
  `dagstak_kw`, `time_tak_kw`, `dagens_maks_kw`, `topp_2_andre_dager_kw` og
  `kan_legge_paa_kw` erstatter `next_tier_threshold_kw`,
  `effective_threshold_kw`, `topp_2_snitt_denne_maned_kw` og resten. Leser du
  attributter i egne maler, må de byttes.
- **Kostnadssensoren viser hva timen koster nå**, og hoppet til neste trinn
  ligger i attributtet `kostnad_neste_trinn_kr`. Før sto månedsprisen for
  trinnet fast som tilstand hele måneden.
- **Førstegangsoppsettet spør ikke lenger om sikkerhetsmargin, holdetid,
  minste risikonivå og strategi.** Ingen kan svare på det før integrasjonen har
  kjørt en uke. De ligger i Configure, med de samme standardverdiene som før.

### Internt

- Regnestykkene er flyttet ut av coordinatoren og inn i fem moduler uten en
  eneste Home Assistant-import, så terskelmodellen, timeregnskapet, hysteresen,
  de kuttbare lastene og trinn-tabellen kan regnes og testes uten stubber.
  `coordinator.py` gikk fra 1150 linjer til å være ticket som kaller dem.
- Testene kjører mot to ekte Home Assistant-versjoner i tillegg til
  enhetssuiten: 2025.1.0, som er minimumet `hacs.json` lover, og den nyeste vi
  har sett på. Matrisen fant to feil ingen av enhetstestene kunne se.
- Release-pakken bygges fra git-objektene på commiten taggen peker på, så den
  er bit-identisk fra samme commit og kan bygges opp igjen av hvem som helst.
  Den attesteres med GitHubs artifact attestation. Hvordan du etterprøver det,
  står i [SECURITY.md](SECURITY.md).
