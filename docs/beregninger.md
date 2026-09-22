# Beregninger

Implementasjon, alt sammen ren Python uten Home Assistant-import:
[`modell.py`](../custom_components/effektvakt/modell.py) (terskler, projeksjon, risiko og kostnad),
[`timeregnskap.py`](../custom_components/effektvakt/timeregnskap.py) (integrasjon, måleravstemming og dagsmaks),
[`hysterese.py`](../custom_components/effektvakt/hysterese.py),
[`laster.py`](../custom_components/effektvakt/laster.py) (tilgjengelig kutt) og
[`const.py`](../custom_components/effektvakt/const.py) (konstantene).
[`coordinator.py`](../custom_components/effektvakt/coordinator.py) regner ikke selv: den leser sensorene gjennom [`avlesning.py`](../custom_components/effektvakt/avlesning.py), kaller filene over i rekkefølge og legger svarene i data-dicten sensorene leser.

## Projisert time-snitt

Hvert tick beregnes forventet time-snitt i kW ved time-slutt:

```
projected_avg = actual_kwh_this_hour + current_kw * remaining_h
```

Hvor:

- `actual_kwh_this_hour`: energi målt hittil denne timen (kWh)
- `current_kw`: øyeblikkelig effekt fra power-sensor (kW)
- `remaining_h`: andel av timen som gjenstår (`1.0 - elapsed_h`)
- `elapsed_h`: `(now.minute + now.second / 60) / 60`

Eksempel kl. 18:45, 2,4 kWh brukt, 3,2 kW nå:

```
elapsed_h      = (45 + 0/60) / 60 = 0.75
remaining_h    = 1.0 - 0.75 = 0.25
projected_avg  = 2.4 + 3.2 * 0.25 = 3.2 kW
```

Tidlig i timen er tallet nesten bare framskrivning, og en last som slås på der løfter det med nesten hele sin effekt. Projeksjonen er likevel riktig som den står, for den svarer på «hvor ender timen om det fortsetter slik». At den ikke kan tas på ordet som grunnlag for å kutte, håndteres i [kuttkriteriet](#kuttkriteriet-flytter-denne-timen-trinnet).

### `actual_kwh_this_hour`

Timen bygges av to kilder som avstemmes mot hverandre, ikke av energy-sensoren alene.

**Effektintegrasjon hvert tick.** Energien mellom to tick er trapesregelen over de to
effektavlesningene, med faktisk tid mellom tidsstemplene:

```
kwh = (forrige_kw + na_kw) / 2 * timer_mellom_ticks
```

Tiden hentes fra tidsstemplene og ikke fra et antatt tickintervall, for ticket hopper over
når HA har det travelt. Trapesregelen framfor å holde den forrige avlesningen: en last som
slås av og på treffer like ofte før som etter en avlesning, og da er midtverdien uten
systematisk slagside. Går det mer enn fem minutter mellom to tick, har HA vært nede eller
stått fast, og da integreres intervallet ikke i det hele tatt (se `MAX_INTEGRATION_GAP_H` i
`timeregnskap.py`).

Siste effektavlesning lagres, så en omstart som tar under fem minutter integreres over
med den effekten som sto da HA gikk ned. Det er et anslag, men et bundet et, og
energy-sensoren retter det ved neste avlesning.

**Energy-sensoren korrigerer.** Måleren er den nøyaktige kilden og skal vinne, men den
legges ikke oppå anslaget. `Timeregnskap` holder rede på hvor mye av timen som er integrert
anslag og ikke bekreftet av måleren (`estimert_siden_maaler_kwh`), og når måleren flytter
seg byttes nettopp den delen ut:

```
actual_kwh_this_hour = actual_kwh_this_hour - estimert_siden_maaler + maalerens_andel
```

Dermed telles ingenting to ganger, og en måler som oppdaterer hvert tiende sekund gir
nøyaktig sin egen differanse. Står måleren stille, er det ingenting å avstemme, og
anslaget får stå. Vi kan ikke se forskjell på en måler med null forbruk og en som bare
ikke har rapportert ennå.

Går måleren ned, er den nullstilt eller byttet. Hopper den mer enn `MAX_ENERGY_DELTA_KWH`,
er avlesningen ikke til å stole på uansett. I begge tilfeller beholdes det som alt er målt
denne timen, og tellingen fortsetter fra den nye standen.

Uten energy-sensor er integrasjonen alt som finnes, og timen blir like god som
effekt-sensoren og tick-frekvensen tillater. Typisk 1-5 % avvik over en time.

### kWh som kommer etter timeskiftet

En norsk HAN-avleser rapporterer gjerne 13 sekunder på timen, altså etter at timen den
måler er over. Den kWh-en hører til timen før. Tre ting gjør at den havner riktig:

1. **Tidspunktet er målerens, ikke ticket sitt.** `last_changed` på energy-sensoren sier
   når måleren faktisk meldte seg. Ticket som leser den kommer gjerne et halvt minutt
   senere, og brukes det tidspunktet i stedet, havner hele timen på feil side av skiftet.
2. **Timeskiftet deler integrasjonen.** Ligger et timeskifte mellom to tick, interpoleres
   effekten ved skiftet og energien deles i to. Den delen som lå før, følger med over til
   timen som ble ferdig.
3. **Timen holdes åpen for retting.** `Timeregnskap._finalize_hour` låser timen inn med det vi vet ved
   timeskiftet, men beholder den som en `VentendeTime` med `dagsmaks_foer`, altså
   dagsverdien slik den sto før. Kommer avlesningen som dekker skiftet, byttes den
   estimerte delen ut og timen låses inn på nytt, også nedover. Så snart måleren har
   bekreftet tiden forbi skiftet, er timen gjort opp og kan ikke ta imot mer.

Fordelingen av en måleravlesning mellom de to timene følger anslaget, ikke tiden: måleren
sier hvor mye som gikk med, integrasjonen sier når. Vekten er ikke anslaget rått, men
snitteffekten vi faktisk målte ganget med den tiden av måler-vinduet som ligger i timen.
Forskjellen betyr noe når HA kom opp igjen fem minutter før timen var omme: fem minutter
med anslag er for lite til å veies mot tretten sekunder av den neste timen, og uten
skaleringen ville den nye timen fått en tiendedel av forrige times kWh i fanget. Er
anslaget null, altså ingen effekt-sensor, deles det på tid i stedet. Rekker vinduet mellom to avlesninger lenger
tilbake enn de to timene vi kan rette på, skaleres kWh-en ned til den andelen av tiden som
faktisk lar seg plassere. Resten hører til timer som er låst, og å legge den på timen vi
står i ville bygget en falsk topp.

### `kwh_maalt_fra_minutt`

Hvilket minutt av den inneværende timen vi har sammenhengende måling fra. Null i normal
drift. Over null betyr at `actual_kwh_this_hour` mangler starten av timen, og da er
projeksjonen for lav. Det skjer i to tilfeller:

- Integrasjonen ble satt opp midt i en time. Vi kan ikke integrere bakover, og finner ikke
  på et tall for det vi ikke så.
- HA var nede lenger enn `MAX_INTEGRATION_GAP_H`, eller effekt-sensoren var utilgjengelig.

Dekningen utvides av seg selv så snart energy-sensoren rapporterer en avlesning som rekker
tilbake til før hullet, for den kWh-en inneholder det vi gikk glipp av. Med en timesmåler
skjer det ved neste timeskifte. Uten energy-sensor står hullet ut timen. Tallet ligger i
coordinator-data og i diagnostikken, og er ikke en egen sensor.

---

## NVE-modellen for kapasitetstrinn

Norske nettselskap bruker snittet av de tre høyeste time-forbrukene fra tre ulike dager. `Timeregnskap` i `timeregnskap.py` fører dagsmaksene, `top_n_average` i `modell.py` regner snittet:

1. For hver fullført klokketime, ta `actual_kwh_this_hour` som timer-forbruk.
2. Sammenlign mot beste registrerte time samme dag. Oppdater hvis høyere.
3. `daily_max_kw` inneholder én verdi per dag: høyeste registrerte time den dagen.
4. `topp_3_snitt` = sum av de inntil 3 høyeste verdiene i `daily_max_kw`, alltid delt på 3.

Delingen på 3 også med færre enn tre dager er det som gjør tallet monotont: en rolig dag nummer tre skal ikke dra snittet ned og gi inntrykk av at noe ble reddet. Dagene som ikke finnes ennå teller som null, og da er tallet samtidig en nedre skranke for hva måneden kan ende på.

Dagsverdien settes med max mot det dagen hadde før timen ble lagt inn, ikke mot det den
har nå. Forskjellen betyr noe når en måleravlesning retter den timen som nettopp ble låst
inn: rettingen skal også kunne gå nedover, uten at den må konkurrere med seg selv. En
omstart som kjører innlåsingen på nytt for den samme timen kan fortsatt ikke telle dobbelt.

Dette er dag-snitt av maks-timer, ikke rå time-verdier. Modellen er identisk med Elhubs metode for kapasitetstrinn-bestemmelse.

---

## Terskelmodellen

Hele modellen ligger i [`modell.py`](../custom_components/effektvakt/modell.py), som er ren Python uten Home Assistant-import. Risiko, margin, kostnad og «kan legge på» regner fra det samme taket, så de kan ikke si hver sin ting om den samme timen.

Fram til september 2026 fantes tre ulike terskler i tre funksjoner, og de var uenige. `compute_effective_threshold` ga `max(neste terskel, snitt av topp-2 dager)`, altså motsatt vei av regelen: den hevet terskelen når de andre dagene var høye. To dager på 6,0 og 5,8 ga «terskel 5,90» når den ekte grensen var 3,20.

### Måltrinnet: T

Det billigste kapasitetstrinnet måneden fortsatt kan ende på. Det er trinnet `minste_mulige_topp_3_kw` havner i, og terskelen til det trinnet er `T`.

```
minste_mulige_topp_3_kw = sum av inntil tre høyeste daily_max_kw / 3
T                       = øvre terskel for trinnet det tallet havner i
```

Skranken teller bare dagsmaks som alt er låst inn, og deler alltid på tre. Den kan derfor bare stige gjennom måneden, og den sier hvor lavt måneden kan ende uansett hva som skjer videre.

Måltrinnet følger ikke projeksjonen. Det er med vilje: fulgte det den, ville referansen flyttet seg oppover i samme øyeblikk som en time spratt over terskelen, og varselet forsvunnet akkurat når brukeren burde kuttet. Det var også det som gjorde at marginen målte mot noe annet enn brukeren trodde (`sensor.effektvakt_margin_til_neste_trinn` viste 3,50 med projisert 0,38, fordi den lave projeksjonen valgte 2 kW-trinnet som «neste»).

### Dagstaket: x\*

Hvor høy dagen i dag kan bli uten å dra topp-3-snittet over T. Snittet av de tre høyeste er `(a + b + x) / 3`, der `a` og `b` er dagsmaks for de to høyeste **andre** dagene:

```
(a + b + x) / 3 <= T     =>     x <= 3T - (a + b)

dagstak_kw = min(T, 3T - (a + b))
```

Jo høyere de andre dagene er, jo mindre tåler dagen i dag. Det er hele poenget, og det er motsatt av hva koden gjorde før.

Kappet ved T er en policy, ikke aritmetikk. Ukappet kunne én dag tatt hele budsjettet de tre plassene deler, og da måtte resten av måneden holdt seg nær null. Kappet gir hver av de tre dagene lik andel.

Mot BKKs 5 kW-trinn (250 kr), der neste trinn er 10 kW (415 kr):

| Andre dager  | `3T - (a + b)` | `dagstak_kw` | Gammel modell |
| ------------ | -------------- | ------------ | ------------- |
| 6,0 og 5,8   | 3,2            | **3,20**     | 5,90          |
| 5,5 og 5,5   | 4,0            | **4,00**     | 5,50          |
| 2,0 og 2,0   | 11,0           | **5,00**     | 5,00          |

De to første meldte god margin mens brukeren var langt over. Den tredje traff riktig svar av feil grunn.

### Timetaket: det marginen måles mot

Dagen teller bare med sin høyeste time, så en time under dagens eget dagsmaks flytter ingenting:

```
time_tak_kw = max(dagens_maks_kw, dagstak_kw)
margin_kw   = time_tak_kw - projisert_time_snitt
```

Da blir domeneregelen sann i koden og ikke bare i README: er dagens topp alt blant de tre høyeste, koster en ny time på samme nivå ingenting.

Eksempel: dagene 1,0 / 1,0 / 12,0, der 12,0 er i dag. Skranken er 14 / 3 = 4,67, altså 5 kW-trinnet, og dagstaket er kappet til 5,0. Men dagen har alt satt 12,0, så timetaket er 12,0. En time på 11 kW har 1 kW margin; en time på 13 kW flytter dagsmaksen og dermed måneden.

### Ingen terskel å måle mot

`maal_terskel_kw`, `dagstak_kw`, `time_tak_kw`, `margin_kw` og `kan_legge_paa_kw` er alle `null` i to tilfeller: ukjent nettselskap (tomt trinn-sett) og måned som alt ligger på øverste trinn. Da finnes det ikke noe dyrere trinn å unngå. Risikoen er `god_margin`, og `kutt_anbefalt_kw` er 0.

Det står `null` og ikke uendelig med vilje: `inf` er ugyldig JSON og knekker både recorder og websocket.

---

## Kostnad for neste trinn

`compute_kostnad` i `modell.py` regner ut hva kapasitetsleddet koster og hva som står på spill akkurat nå. Resultatet mater `sensor.effektvakt_kostnad_neste_trinn`.

Først: hvilket trinn ligger måneden an til?

```
projiserte_dager       = daily_max_kw, men dagens verdi byttes ut med
                         max(daily_max_kw[i dag], projisert_time_snitt)
topp_3_projisert_kw    = snitt av de 3 høyeste i projiserte_dager
```

Trinnet er det laveste med terskel >= `topp_3_projisert_kw`. Over høyeste terskel havner du på øverste trinn. Derfra:

```
trinn_na_kr                = månedspris for det trinnet
trinn_na_ovre_grense_kw    = terskelen for det trinnet (null på øverste trinn)
trinn_neste_kr             = månedspris for trinnet over (null på øverste trinn)
kostnad_neste_trinn_kr     = trinn_neste_kr - trinn_na_kr   (0 på øverste trinn)
besparelse_trinn_under_kr  = trinn_na_kr - pris for trinnet under   (0 på laveste)
```

Prisene er flate månedspriser. Ingen pro rata, så tallet er like stort den 1. som den 28. Det er hele månedsregningen som står på spill uansett når i måneden toppen settes.

### `minste_mulige_topp_3_kw`

Nedre skranke for hva måneden kan ende på, og samtidig tilstanden til `sensor.effektvakt_topp_3_snitt_denne_maned` og grunnlaget for måltrinnet:

```
minste_mulige_topp_3_kw = sum av inntil 3 høyeste daily_max_kw / 3
```

Bare dagsmaks som alt er låst inn telles. Den inneværende timen holdes utenfor nettopp fordi den fortsatt kan kuttes. Å telle den med ville gjort tallet pessimistisk og kunne sagt at trinnet under er uoppnåelig når det faktisk er innen rekkevidde.

```
trinn_under_oppnaelig = minste_mulige_topp_3_kw <= terskel for trinnet under
```

Én dag på 7 kW gir 2,33 og trinnet under er oppnåelig. Tre dager på 6, 7 og 8 gir 7,0, og da er løpet kjørt.

### `kostnad_denne_timen_kr`

Kronene den inneværende timen er i ferd med å låse inn, og tilstanden til `sensor.effektvakt_kostnad_neste_trinn`:

```
kostnad_denne_timen_kr = pris for trinnet topp_3_projisert_kw gir
                         - pris for trinnet minste_mulige_topp_3_kw gir
```

Begge tallene deler på 3, så det projiserte ligger aldri under skranken og differansen er aldri negativ. Klemmen mot null står igjen som en sikring mot egendefinerte trinn-tabeller der prisen ikke stiger med terskelen.

### Kostnaden og marginen sier ikke det samme, men de motsier hverandre ikke

Marginen slår ut på eller før kostnaden, aldri etter. Er `margin_kw` null eller positiv, er `kostnad_denne_timen_kr` alltid 0. Den invarianten er testet med hypothesis i `tests/test_kostnad.py`.

Den andre veien er tillatt: marginen kan være negativ mens timen ennå ikke koster noe. Det skjer når dagstaket er kappet ved T. To dager på 4,0 og en projeksjon på 5,0 holder måneden i 5 kW-trinnet (13 / 3 = 4,33), men dagen er over sin andel av de tre plassene, og fortsetter resten av måneden i samme spor ryker trinnet. Timen koster ikke noe ennå, den bruker opp slarken. Det er den konservative retningen, og det er den et varsel skal ha.

### Uendelig øverste terskel

Øverste kapasitetstrinn har `float("inf")` som terskel i `dso.py`. `inf` er ugyldig JSON og knekker både recorder og websocket, så både `trinn_na_ovre_grense_kw` og øverste par i `kapasitetstrinn`-attributtet sendes som `null`.

### Ukjent nettselskap

Tomt trinn-sett gir `None` på alle ti kostnadsfeltene, og sensoren står som `unknown`.

---

## Kuttkriteriet: flytter denne timen trinnet?

Projeksjonen ganger den øyeblikkelige effekten med resten av timen. Ved minutt to er nesten hele tallet framskrivning, og en vannkoker på 2 kW oppå 3,5 kW grunnlast gir projisert 5,4 kW mot et tak på 5,0. Timen ender på 3,6. Fram til september 2026 var det nok til å kutte berederen, og det er den feilen `vurder_kuttkriterium` i `modell.py` retter.

Kriteriet for å kutte er kroner, ikke geometri. `kostnad_denne_timen_kr` er prisen timen er i ferd med å låse inn, altså prisen på trinnet vi ligger an til minus prisen på trinnet dagene alene gir. Er den null, koster timen ingenting uansett hvor dramatisk projeksjonen ser ut, og topp-3-regelen gjør at de fleste timer er nettopp det.

Prisen regnes ikke av projeksjonen rå, men av `varig_projeksjon_kw`:

```
kortvarig_paaslag_kw = KORTVARIG_LAST_KW × (1 − elapsed_h)
varig_projeksjon_kw  = max(actual_kwh_this_hour, projected_avg − kortvarig_paaslag_kw)
```

En last på P kW som slås på ved `e0` løfter projeksjonen med `P × (1 − e0)` og holder den der så lenge den går, mens den ekte virkningen på time-snittet bare er `P × varigheten`. Fradraget har derfor samme form: det er akkurat det en last på `KORTVARIG_LAST_KW` ville lagt på om den ble slått på nå. Ved minutt null er det 1,5 kW, ved minutt tretti 0,75, og når timen er omme er det null og projeksjonen er målt faktum. Gulvet er kilowattimene timen alt har brukt; de kan ikke kuttes bort igjen, så fradraget skal aldri ta oss under dem.

### Avveiningen

Ventingen koster noe. Et varsel som kommer for sent er like ubrukelig som et som kommer for tidlig, for verdien av et kutt faller med resten av timen: kutter du 2 kW ved minutt ti, forsvinner 1,67 kW av time-snittet, ved minutt femti bare 0,33.

At begge sidene skalerer med `1 − elapsed_h` er det som holder avveiningen på plass. Fradraget slipper taket når overskridelsen passerer `KORTVARIG_LAST_KW × (1 − elapsed_h)`, og et kutt som står igjen på samme tidspunkt henter inn `kuttet × (1 − elapsed_h)`. **Er den kuttbare lasten minst like stor som `KORTVARIG_LAST_KW`, rekker kuttet alltid å hente inn hele overskridelsen**, uansett når i timen den dukker opp. Derfor er 1,5 kW satt under de 2 kW en varmtvannsbereder trekker.

Prisen er at små overskridelser varsles sent. En vedvarende time på 6,0 kW mot et tak på 5,0 meldes rundt minutt tjue, ikke ved minutt null, og en på 5,2 kW først rundt minutt femti. Har du bare 0,3 kW kuttbar last, altså `blind`-strategien uten sensorer, kommer varselet i praksis for sent til at kuttet berger timen; men 0,3 kW hadde uansett ikke berget den. Tallet hører hjemme i `const.py` som `KORTVARIG_LAST_KW`, og skal kalibreres mot ekte drift framfor mot følelsen av at det er for tregt.

---

## Risikoklassifisering

`classify_raw_risk` i `modell.py` bestemmer rå risiko av margin, konfigurert `safety_buffer_kw` (standard 1,0 kW) og kuttkriteriet over:

| Betingelse                      | Risiko                |
| ------------------------------- | --------------------- |
| `margin > 2 × buffer`           | `god_margin`          |
| `buffer < margin <= 2 × buffer` | `naermer_seg_terskel` |
| `0 < margin <= buffer`          | `like_under_terskel`  |
| `margin <= 0`                   | `over_terskel`        |

Margin = `time_tak_kw - projected_avg`, se [terskelmodellen](#terskelmodellen). Er `margin_kw` `null`, altså ukjent nettselskap eller øverste trinn, er risikoen `god_margin`: det finnes ikke noe dyrere trinn å advare mot.

Kuttkriteriet er et veto over tabellen. **De to øverste nivåene er forbeholdt timer som faktisk koster penger.** Er `timen_flytter_trinnet` usann, settes nivået ned til `naermer_seg_terskel` uansett hvor høyt projeksjonen står. Vetoet ligger i klassifiseringen og ikke i binærsensoren nettopp fordi det ikke skal kunne omgås av `min_risiko_for_kutt`: det er en retting av hva projeksjonen er verdt, ikke en preferanse.

Sikkerhetsbufferen er dermed ikke lenger noe som utløser kutt alene. Jobben den har igjen er forvarselet: den bestemmer hvor tidlig `naermer_seg_terskel` lyser, så et dashbord eller en varslings-blueprint kan si fra før automatikken griper inn.

En følge av vetoet er at `like_under_terskel` ikke lenger kan oppstå som rå nivå. Kriteriet er oppfylt bare når den varige projeksjonen alt ligger over taket, og den er aldri høyere enn projeksjonen selv, så marginen er negativ og nivået `over_terskel`. Er kriteriet ikke oppfylt, settes nivået ned til `naermer_seg_terskel`. Verdien lever videre i sensoren, for hysteresen går innom den på vei ned fra `over_terskel`, og `min_risiko_for_kutt` kan fortsatt stå på den; forskjellen fra `over_terskel` er da at kuttet holdes ett hysteresetrinn lenger. Invarianten står som hypothesis-test i `tests/test_tidlig_i_timen.py`.

---

## Hysterese

Rå risiko går direkte inn i `apply_hysteresis` i [`hysterese.py`](../custom_components/effektvakt/hysterese.py). Regler:

- **Oppgang** (høyere risiko): umiddelbar. Ingen ventetid.
- **Nedgang** (lavere risiko): ett trinn av gangen. Hvert trinn ned krever at det lavere nivået holder seg i `risiko_holdetid_minutter` (standard 5 min).
- Multi-step: fra `over_terskel` til `god_margin` skjer via `over_terskel -> like_under_terskel -> naermer_seg_terskel -> god_margin`, med ny tidtaker per trinn.

Eksempel: Risiko er `over_terskel`. Rå risiko faller til `god_margin`. Etter 5 min uten ny `over_terskel` settes risiko til `like_under_terskel`. Etter ytterligere 5 min til `naermer_seg_terskel`. Etter 5 min til til `god_margin`.

Dette forhindrer at VVB eller panelovn slås raskt av og på ved forbruk som svinger rundt en grense.

---

## Adaptiv tick-frekvens

Coordinator-intervallet justeres basert på risiko-nivå, etter `TICK_INTERVAL_BY_RISIKO` i `const.py`:

| Risiko                | Intervall   |
| --------------------- | ----------- |
| `god_margin`          | 60 sekunder |
| `naermer_seg_terskel` | 60 sekunder |
| `like_under_terskel`  | 30 sekunder |
| `over_terskel`        | 15 sekunder |

Er terskelen passert, leses sensorer og projeksjon oppdateres hvert 15 sekund for rask respons.

---

## Tilgjengelig kutt per strategi

`compute_tilgjengelig_kutt_kw` i `laster.py`:

| Strategi           | Logikk                                                                  |
| ------------------ | ----------------------------------------------------------------------- |
| `blind`            | Returnerer `BLIND_ASSUMED_KUTT_KW` = 0,3 kW (2 kW VVB × 15% duty cycle) |
| `vvb_status`       | VVB-effekt / 1000 hvis VVB > 1000 W, ellers 0,0 kW                      |
| `vvb_pluss_ekstra` | VVB-bidrag + sum av ekstra-sensorer > 100 W terskel                     |

Terskelen på 1000 W for VVB er satt fordi elementet er enten fullt på (~2 kW) eller av. Verdier mellom 0 og 1000 W antas å være standby-forbruk, ikke aktiv oppvarming.

---

## DST-håndtering

Time-bucket bestemmes av `(now.hour, now.utcoffset())`. Ved overgang til/fra sommertid endres utcoffset, noe som fanger klokkeskiftet uten å forveksle det med et vanlig time-skifte. Klokken 02:00 (DST frem) og 03:00 (DST tilbake) håndteres korrekt uten å lage dobbel- eller manglende time-registrering.
