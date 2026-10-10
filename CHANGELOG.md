# Endringslogg

Alt som merkes av den som bruker Effektvakt, står her. Formatet er [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), og versjonene følger [SemVer](https://semver.org/).

Punktene som er merket `<!--kort-->` er de som havner i den korte release-noten, altså teksten HACS viser i oppdateringspanelet inne i Home Assistant. Resten står bare her. Overskriften får utgivelsesdatoen sin den dagen versjonen faktisk går ut; fram til da sier den «Ikke sluppet», og release-flyten nekter å slippe en versjon uten dato.

## [0.5.0] - Ikke sluppet

### Lagt til

- Valgfritt mål for månedens kapasitetstrinn. Du kan for eksempel sikte mot 5 kW fra første dag i måneden. Det kan gi tidligere og flere lastkutt for å holde målet innen rekkevidde; målet slutter å styre kuttene hvis allerede registrerte topper har gjort det umulig. Standardinnstillingen er uendret. [Slik virker månedsmålet](docs/sparepotensial.md#et-mål-for-måneden). <!--kort-->
- Valgfrie lastprofiler fra siste ukes historikk eller manuell nominell effekt og arbeidssyklus. En ny sensor viser estimert kuttenergi resten av timen; målt tilgjengelig kutt beholder kW. Profilgrunnlaget vises per last. Du kan velge å bruke det i kuttvurderingen for målte aktive laster; manuelle profiler uten måling gir bare planleggingsanslag. [Lastprofiler](docs/lastprofiler.md). <!--kort-->
- Verktøy for å hente effekthistorikk fra Home Assistant, analysere lastenes målte påandel, effekt og sykluslengder og simulere lastkutt med utsatt forbruk som må inn igjen. De kjøres lokalt fra repoet og endrer ikke styringen i Home Assistant. [Eksport og analyse](docs/lastprofiler.md#eksporter-historikken-fra-home-assistant) og [sparepotensial og forutsetninger](docs/sparepotensial.md).
- Historikkprofilene hentes fra recorder i bakgrunnen ved oppstart og hver time. Egne utkoblinger holdes utenfor læringen, også etter omstart. Profilene viser målevindu, datadekning og antall støttende sykluser; manglende historikk gir ukjent anslag.

### Dokumentasjon

- Årsregneeksempel med andel av kapasitet og samlet kostnad, og scenarioer for vask i lavpristiden, spotpris og høyere Norgespris. FAQ forklarer betydningen av elbil, oppvarming og solceller.
- README er kortet ned, med spareeksemplet og installasjonen først. Lastprofiler, regnestykkene og simuleringen har egne norske veiledninger, med en etterprøvbar eksempelrapport for den som vil undersøke sitt eget anlegg.

## [0.4.0] - 2026-10-09

Betaversjon. Denne versjonen retter beregningene og laststyringen og kan installeres og oppdateres gjennom HACS.

### Dette må du gjøre selv

- Bruker du lastkutt-blueprints fra en eldre versjon, importer [blueprintene](docs/blueprints.md) på nytt. De bruker nå integrasjonens lastvern til å koble lastene inn igjen.
- Leser dine egne maler sensorattributter, må du oppdatere navnene som er endret. Se [sensoroversikten](docs/sensorer.md).

### Endringer fra 0.3.0

- Rettet beregningen av hvor mye dagen tåler før månedens topp-3-snitt gir dyrere nettleie. Høye topper på andre dager skal redusere marginen. Timen bygges nå opp fra effektsensoren mellom avlesningene fra energimåleren, også med HAN-målere som rapporterer energi én gang i timen. <!--kort-->
- Lastkutt tar hensyn til hvor mye av timen som er igjen og om kuttet kan påvirke kapasitetsleddet. Lastvernet husker lastene det har kuttet gjennom omstart og omlasting, og kobler dem inn igjen ved timeskiftet eller når tidsgrensen er nådd. <!--kort-->
- Oppdaterte kapasitetstariffer fra 1. oktober. Nettselskap med andre eller uverifiserte tariffmodeller får beskjed om begrensningen. Manglende eller gamle målinger gir ukjent råd. <!--kort-->
- Rettet oppsettsdialogen og innlasting av dashbordkortet. Oppsett, sensortekster og kort er tilgjengelige på norsk og engelsk. <!--kort-->

### Funksjonsoversikt

- Effektvakt sier fra før timen låser inn et dyrere kapasitetstrinn. Seks sensorer: projisert time-snitt, margin til neste trinn, topp-3-snitt for måneden, risikonivå, tilgjengelig kutt og hva timen koster. Pluss `binary_sensor.effektvakt_kutt_ned_anbefalt`, som automasjoner trigger på, og `switch.effektvakt_automatikk` som hovedbryter. Alle sammen i [docs/sensorer.md](docs/sensorer.md).
- Et kort til dashboardet som gjenskaper den analoge effektvakten fra kjøkkenveggen. Skiven tegnes av dine egne kapasitetstrinn, så kronebeløpene på buen er prisene nettselskapet ditt faktisk tar. Rød viser er projeksjonen, den tynne svarte er effekten akkurat nå, og trekanten utenfor buen er månedens topp-3-snitt. Kortet følger med integrasjonen og serveres derfra, det skal ikke installeres for seg.
- Kapasitetstrinn for 71 norske nettselskap, hentet rett fra [fri-nettleie](https://github.com/kraftsystemet/fri-nettleie) på en pinnet commit og en pinnet tariffdato. Tabellen kan etterprøves mot kilden med én kommando, og CI feller hvis den har drevet. Har du et selskap som ikke står i listen, kan du skrive trinnene selv for topp-3-modellen. Andre eller uverifiserte tariffmetoder kan ikke brukes til styringsråd ennå. [docs/dso.md](docs/dso.md).
- Fire blueprints for varmtvannsbereder, panelovner, en generell last og ren varsling. De tre lastkutt-blueprintene bruker lastvernet til å be om gjeninnkobling ved neste timeskifte, fordi verdien av et kutt slutter der. [docs/blueprints.md](docs/blueprints.md).
- Svar på hva timen faktisk tåler. Alle sensorene bærer `minutter_igjen_av_timen` og `kan_legge_paa_resten_av_timen_kw`: med ett kW margin klokka 18:50 er svaret 6 kW, ikke 1 kW, fordi en last som står i ti av seksti minutter bare flytter snittet med en sjettedel av effekten sin. Topp-3-sensoren sier hvilke tre dager snittet består av, om dagen i dag alt teller med, og hvilken dag en høyere time ville skjøvet ut.
- Watchdog. Henger coordinatoren i mer enn to minutter, settes sensorene til `unknown` framfor å stå igjen med gamle tall. Automasjoner kan skille «vet ikke» fra «alt er fint».
- Reparasjonssaker når trinn-tabellen ikke er hel. Peker oppsettet ditt på et nettselskap som er fjernet fra kilden, eller mangler egendefinerte trinn et åpent øverste trinn, får du beskjed framfor en sensor som stille sier «god margin» for alltid.
- Diagnostikk kan lastes ned fra integrasjonssiden og legges ved en feilrapport. Den viser oppsett, målegrunnlag og lastvernets aktive kutt og gjeninnkoblingsfrister.

### Fikset

- Oppdatert kapasitetstrinn fra 1. oktober 2026 for Asker, Barents, Glitre, Kystnett, Midtnett og Norgesnett
- Etna gir ukjent økonomi og styringsråd over 25 kW, og Nettselskapet fra og med 75 kW, fordi tariffgrunnlaget da er utenfor kildebekreftet omfang.

Feilrettingene under gjelder beregninger og gjeninnkobling i tidligere versjoner.

- Gjeninnkoblingen overlever reload og omstart. Lastvernet husker hvilke laster det faktisk overtok, originaltemperaturen og fristen. Det prøver igjen når en utilgjengelig aktuator kommer tilbake. Slått av automatikk og nye risikohendelser avbryter ikke ansvaret. Minste påtid kan ikke lenger omgås av blink i sensoren. [docs/blueprints.md](docs/blueprints.md).
- Manglende målinger gir ukjent råd. Ugyldig eller utdatert effekt blir ikke behandlet som null forbruk med ledig kapasitet. Måledekning og coordinatorens friskhet vises hver for seg.
- Sommertidsskiftet regnes i faktisk tid. De to 02-timene om høsten holdes atskilt når effekt integreres og måleravlesninger fordeles.
- Feil tariffmodell gir en forklaring. Sør Aurdal Energi bruker månedsmaks, og Tinfos har uverifisert metode. Disse får ikke lenger topp-3-råd; nye oppsett forklarer begrensningen og eksisterende oppsett får et repair-varsel. Trinnprisene beholder ørene fra kilden.
- Kuttbehovet tar hensyn til resten av timen. Nødvendig momentan lastreduksjon skilles fra reduksjonen i timegjennomsnitt. Tilgjengelig kuttbar last og allerede brukt energi inngår når et kutt vurderes, så små laster kan hjelpe tidsnok og tapte timer ikke fremstilles som reddbare.

- Terskelen gikk rett vei, men regnestykket gikk feil vei. Effektvakt regnet med at jo høyere de andre dagene i måneden var, jo mer tålte dagen i dag. Topp-3-regelen sier det motsatte. Mot BKKs 5 kW-trinn meldte den gamle modellen 5,90 kW der grensen var 3,20, og 5,50 der den var 4,00: god margin, mens du var langt over. Hele terskelaritmetikken ligger nå ett sted, og margin, risiko, kostnad og «kan legge på» regner alle fra det samme taket. [docs/beregninger.md](docs/beregninger.md).
- Timen sto på 0,000 kWh med en vanlig norsk HAN-avleser. Forbruket ble bygget utelukkende av differanser på energisensoren, og en HAN-avleser rapporterer én gang i timen. Projeksjonen kollapset dermed mot øyeblikkseffekten nettopp mens timen ble låst inn. Timen bygges nå opp av effektsensoren mellom hver avlesning, og energimåleren retter den etterpå, uten at de to legges oppå hverandre. kWh som kommer etter timeskiftet havner på timen før, og en oppstart midt i timen sier hvilket minutt vi har sammenhengende måling fra framfor å gjette.
- En vannkoker tidlig i timen kuttet varmtvannsberederen. To minutter inn i timen er projeksjonen nesten bare øyeblikkseffekt, så 2 kW oppå 3,5 kW grunnlast ble til «over terskelen» selv om timen endte på 3,6. Kriteriet er nå kroner og ikke geometri: de to øverste risikonivåene krever at timen faktisk koster noe, regnet med fradrag for hvor mye en kortvarig last rekker å bety i det som er igjen av timen.
- Når du endret sikkerhetsmarginen, ble valgte ekstra effektsensorer og varmtvannssensoren nullstilt. Oppsettsdialogen beholder nå disse valgene. Rettet også en feil som hindret dialogen i å åpne på Home Assistant 2025.12 og nyere.
- Varmtvannsberedere, panelovner og andre laster som blueprintene koblet ut, kunne bli stående utkoblet inn i neste time. Et lastkutt fra 18:50 med 30 minutters tidsgrense varte til 19:20. Lastvernet kobler nå lasten inn igjen ved 19:00, eller tidligere hvis grensen i `max_off_minutes` nås først. For panelovner gjenopprettes temperaturinnstillingen fra før lastkuttet.
- Kortet ga «Fikk ikke hentet skiven» etter omstart og ble stående slik til noen lastet siden på nytt for hånd. Det prøver nå igjen med voksende pause. Samtidig skiller kortet mellom en sensor som er borte og en integrasjon som ennå ikke har målt noe: 0,00 kW er et hus som ikke bruker strøm, og skal ikke stå der vi ikke vet.
- Har du lagt til Effektvakt flere ganger i Home Assistant, for eksempel for to strømmålere, virket handlingene «Sett sikkerhetsmargin» (`effektvakt.set_safety_buffer`) og «Nullstill topp-3-buffer» (`effektvakt.reset_topp_3`) bare på den sist tillagte instansen. De endrer nå sikkerhetsmarginen eller nullstiller månedens registrerte døgnmaks for alle aktive Effektvakt-instanser.

### Endret

- Kuttkriteriet er kroner, ikke geometri. Risikonivåene `over_terskel` og `like_under_terskel` krever nå at timen faktisk flytter kapasitetstrinnet. `like_under_terskel` kan derfor ikke lenger oppstå som rått nivå; den lever videre fordi hysteresen går innom den på vei ned.
- Fellesattributtene på sensorene er navngitt om slik at det står i klartekst hva marginen måles mot: `maal_terskel_kw`, `maal_trinn_kr`, `dagstak_kw`, `time_tak_kw`, `dagens_maks_kw`, `topp_2_andre_dager_kw` og `kan_legge_paa_kw` erstatter `next_tier_threshold_kw`, `effective_threshold_kw`, `topp_2_snitt_denne_maned_kw` og resten. Leser du attributter i egne maler, må de byttes.
- Kostnadssensoren viser hva timen koster nå, og hoppet til neste trinn ligger i attributtet `kostnad_neste_trinn_kr`. Før sto månedsprisen for trinnet fast som tilstand hele måneden.
- Førstegangsoppsettet spør ikke lenger om sikkerhetsmargin, holdetid, minste risikonivå og strategi. Ingen kan svare på det før integrasjonen har kjørt en uke. De ligger i Configure, med de samme standardverdiene som før.
