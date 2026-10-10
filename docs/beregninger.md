# Beregninger

Regnestykkene ligger i [modell.py](../custom_components/effektvakt/modell.py), [timeregnskap.py](../custom_components/effektvakt/timeregnskap.py), [hysterese.py](../custom_components/effektvakt/hysterese.py) og [laster.py](../custom_components/effektvakt/laster.py), uten HA-import. Coordinatoren leser målinger og kaller dem. [Sensoroversikten](sensorer.md) beskriver utdata.

## Projisert time-snitt

```text
projected_avg = actual_kwh_this_hour + current_kw × remaining_h
remaining_h  = 1 − elapsed_h
```

For en klokketime er kWh numerisk lik gjennomsnittlig kW. Klokken 18:45 med 2,4 kWh brukt og 3,2 kW nå blir projeksjonen `2,4 + 3,2 × 0,25 = 3,2 kW`. Tidlig i timen dominerer framskrivningen.

### `actual_kwh_this_hour`

Effekt integreres med trapesregelen og faktisk tid mellom avlesningene:

```text
kwh = (forrige_kw + na_kw) / 2 × timer_mellom_ticks
```

Intervaller over fem minutter integreres ikke. Siste effekt lagres, slik at kortere omstarter kan inngå som anslag. Energimåleren korrigerer uten dobbelttelling:

```text
actual_kwh_this_hour = actual_kwh_this_hour − estimert_siden_maaler + maalerens_andel
```

Bare ubekreftet energi erstattes. Stillestående måler gir ingen korreksjon. Negativ eller for stor målerdifferanse beholder allerede registrert energi og setter nytt anker. Uten energimåler brukes bare effektintegrasjon.

### kWh som kommer etter timeskiftet

Målerens `last_changed` bestemmer avlesningstidspunktet. Effektintegrasjonen deles ved timeskiftet. Forrige time beholdes som `VentendeTime` og kan korrigeres både opp og ned til måleren har bekreftet tiden forbi skiftet.

Målerenergi fordeles mellom timene etter målt snitteffekt og overlappende varighet; uten effektgrunnlag brukes tid. Avlesninger som rekker lenger bakover enn de to timene vi kan korrigere, begrenses til den plasserbare andelen. Eldre forbruk legges ikke på dagens time.

### `kwh_maalt_fra_minutt`

Minuttet sammenhengende dekning begynner. Over null betyr manglende start av timen, for eksempel ved førstegangsoppsett eller lengre målehull. Energimåleren kan fylle hullet senere; uten den består hullet ut timen. Tallet finnes i coordinator-data og diagnostikk.

## NVE-modellen for kapasitetstrinn

For støttet `TRE_DØGNMAX_MND` lagres én dagsmaks per dato: dagens høyeste fullførte timegjennomsnitt. Summen av de inntil tre høyeste deles alltid på tre; manglende dager teller som null. Dette gir en nedre skranke for månedens endelige topp-3-snitt. Sene målerkorreksjoner sammenlignes med dagsmaksen før den aktuelle timen, så timen ikke konkurrerer med seg selv.

`MND_MAX` og ukjent tariffmetode gir ingen operative råd.

## Terskelmodellen

Risiko, margin, kostnad og tilgjengelig påslag bruker samme modell.

### Måltrinnet: T

```text
minste_mulige_topp_3_kw = sum(inntil tre høyeste registrerte dagsmaks) / 3
T = øvre grense for trinnet denne skranken havner i
```

Grunnlaget inneholder avsluttede timer, ikke dagens pågående projeksjon. Et aktivt valgt månedsmål kan erstatte standardmålet; se [månedsmål](sparepotensial.md#et-mål-for-måneden).

### Dagstaket: x*

Med `a` og `b` som de to høyeste dagsmaksene fra andre dager:

```text
(a + b + x) / 3 ≤ T
x ≤ 3T − (a + b)
dagstak_kw = min(T, 3T − (a + b))
```

Høyere topper på andre dager gir mindre rom i dag. Kappingen ved `T` er en konservativ policy som hindrer én dag i å bruke hele tre-dagersbudsjettet. Med `T = 5`, `a = 6,0` og `b = 5,8` blir dagstaket 3,2 kW.

### Timetaket: det marginen måles mot

```text
time_tak_kw = max(dagens_maks_kw, dagstak_kw)
margin_kw   = time_tak_kw − projected_avg
```

En ny time på eller under dagens registrerte topp øker ikke dagsmaksen og flytter ikke månedens trinn.

### Resten av timen

```text
kan_legge_paa_resten_av_timen_kw = max(0, margin_kw) / remaining_h
kutt_anbefalt_kw = max(0, −margin_kw) / remaining_h
```

Ti minutter igjen og 1 kW margin gir 6 kW mulig påslag. Tilsvarende overskridelse krever 6 kW reduksjon resten av timen. Påslaget begrenses til 100 kW; etter timeslutt kan forbruket ikke kuttes bort.

### Ingen terskel å måle mot

På øverste trinn er terskel og margin `null`, risiko `god_margin` og anbefalt kutt 0. Manglende/utdatert måling eller sperret tariff gir derimot ukjent risiko og `beregning_gyldig: false`. Historikken beholdes. `null` brukes fordi uendelig er ugyldig JSON.

## Kostnad for neste trinn

Dagens verdi erstattes med det høyeste av registrert dagsmaks og projeksjonen. Snittet av de tre høyeste gir `topp_3_projisert_kw` og forventet kapasitetstrinn.

```text
kostnad_neste_trinn_kr = pris(neste trinn) − pris(forventet trinn)
besparelse_trinn_under_kr = pris(forventet trinn) − pris(trinnet under)
```

Prisene gjelder hele måneden uten pro rata. Ingen trinn over gir 0 i neste-trinn-kostnad; ingen trinn under gir 0 i mulig reduksjon.

### `minste_mulige_topp_3_kw`

```text
trinn_under_oppnaelig = minste_mulige_topp_3_kw ≤ terskel(trinnet under)
```

Den pågående timen holdes utenfor fordi den fortsatt kan påvirkes.

### Er trinnet under realistisk?

`trinn_under_realistisk` er sann når forrige måneds topp-3-snitt eller snittet av de tre laveste registrerte dagsmaksene er innenfor trinnet under. Uten historikk er svaret falskt. Dette er en historisk vurdering, ikke en garanti.

### `kostnad_denne_timen_kr`

```text
kostnad_denne_timen_kr = max(0, pris(topp_3_projisert_kw) − pris(minste_mulige_topp_3_kw))
```

Dette er kostnadssensorens tilstand: beløpet timen er i ferd med å legge til månedens kapasitetsledd.

### Kostnaden og marginen sier ikke det samme, men de motsier hverandre ikke

Positiv eller manglende margin gir ingen ekstra timekostnad med gyldig tariff. Negativ margin kan forekomme uten ekstra kostnad, fordi dagstaket begrenser dagens andel før fakturert trinn øker.

### Uendelig øverste terskel

Øverste trinngrense lagres internt som `inf` og sendes som `null`. Egendefinerte trinn bruker `[[2, 155], [5, 250], [null, 415]]`. Manglende åpent topptrinn utløser repair.

### Ukjent nettselskap

Tom tabell gir ukjente kostnadsfelt og repair. Eksisterende DSO-nøkler må beholdes; de ligger i brukernes oppsett.

## Kuttkriteriet: flytter denne timen trinnet?

Standardkriteriet krever at tilgjengelig kutt fortsatt kan redusere tariffkostnaden. Et valgt månedsmål kan begrunne tidligere kutt for å begrense en ny dagsmaks.

Kortvarige topper dempes før tariffen vurderes:

```text
kortvarig_paaslag_kw = KORTVARIG_LAST_KW × remaining_h
varig_projeksjon_kw = max(actual_kwh_this_hour, projected_avg − kortvarig_paaslag_kw)
```

Med konstanten 1,5 kW er fradraget 1,5 kW ved timestart, 0,75 halvveis og 0 ved timeslutt. Allerede brukt energi er alltid gulvet.

### Avveiningen

Senere kutt gir mindre bidrag: 2 kW fra minutt 10 reduserer timegjennomsnittet med 1,67 kW; fra minutt 50 bare 0,33 kW. `mulig_besparelse_kr` beskriver kostnadsøkningen fra avsluttede dager, mens `unngaaelig_besparelse_kr` beskriver det tilgjengelig kutt fortsatt kan unngå. Samme trinn etter kutt gir ingen standardanbefaling.

For laster under 1,5 kW finnes også et signal fra minutt 10: målt snitt hittil må gi dyrere tariff, og tilgjengelig kutt må fortsatt senke tariffen. Med 5,2 kW forbruk og 0,3 kW kutt fra minutt 10 blir resultatet 4,95 kWh. Forutsetningen er at lasten ellers ville fortsatt.

## Risikoklassifisering

| Margin før kuttkriterium | Rå risiko |
| --- | --- |
| `margin > 2 × buffer` | `god_margin` |
| `buffer < margin ≤ 2 × buffer` | `naermer_seg_terskel` |
| `0 < margin ≤ buffer` | `like_under_terskel` |
| `margin ≤ 0` | `over_terskel` |

Bufferen er standard 1 kW. Uten oppfylt kuttkriterium begrenses høy rå risiko til `naermer_seg_terskel`. `like_under_terskel` oppstår normalt på vei ned gjennom hysterese.

## Hysterese

Oppgang er umiddelbar. Nedgang skjer ett trinn av gangen, med ny holdetid per trinn (standard fem minutter). Fra `over_terskel` til `god_margin` tar det dermed minst 15 minutter hvis rå risiko holder seg lav.

## Adaptiv tick-frekvens

| Risiko | Intervall |
| --- | --- |
| `god_margin`, `naermer_seg_terskel` | 60 sekunder |
| `like_under_terskel` | 30 sekunder |
| `over_terskel` | 15 sekunder |

## Tilgjengelig kutt

```text
tilgjengelig_kutt_kw = sum(effekt_w der effekt_w > lastens_terskel_w) / 1000
```

Bare gyldige målinger bidrar. Uten målte laster opprettes ikke sensoren. [Lastprofiler](lastprofiler.md) gir et separat energianslag.

## DST-håndtering

Klokketime identifiseres med time og UTC-offset; varighet regnes i faktisk tid. De to lokale 02-timene ved høstskiftet holdes adskilt. Dagsmaks og månedsskifte følger lokal kalender.
