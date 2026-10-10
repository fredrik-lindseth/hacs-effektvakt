# Kuttbare laster

Registrer laster under **Konfigurer → Legg til en kuttbar last**. Du kan også redigere og fjerne dem der. Velg bare forbruk som kan utsettes innenfor lastens behov og tidsgrenser.

| Felt | Bruk |
| --- | --- |
| Effektsensor | Målt aktivitet; kan utelates ved manuell profil. |
| Bryter/aktuator | Valgfri switch eller climate-entitet; bruk samme entitet som blueprinten styrer. |
| Terskel (W) | Lasten teller når målt effekt er strengt over terskelen. Standard 100 W. |
| Navn | Valgfritt visningsnavn; ellers brukes sensorens navn. |

## Terskelen

Velg terskel over standby og under aktiv effekt. Eksempel: en bereder på 2 000 W kan ha terskel 1 000 W; varmekabler på 550 W kan ha 100 W. Bruk målinger fra din last, ikke typeskiltet som bevis på aktivitet.

## Bryteren

Aktuatoren kobler målingen til lastvernets eierskap. `kuttet` betyr at Effektvakt faktisk har overtatt lasten, ikke bare at bryteren er av. Termostatmodus `heat` betyr heller ikke at elementet varmer. Utilgjengelig aktuator gir ukjent tilstand.

Styring opprettes separat med [blueprints](blueprints.md). Å registrere en last lager ingen kutt-automasjon.

## Hva sensoren viser

`sensor.effektvakt_tilgjengelig_kutt` summerer effekten til målte laster over terskelen, i kW. Den opprettes bare med minst én målt last. Manuelle profiler uten måling gir separat energi-estimat.

`kutt_kilder` viser alle konfigurerte laster, også de som ikke teller nå. `effekt_w: null` betyr ukjent, ikke null watt. Se [feltene](sensorer.md#kutt_kilder).

## Et eksempel

En aktiv bereder på 2 000 W og aktive varmekabler på 550 W gir 2,55 kW tilgjengelig kutt. Varigheten avgjør hvor mye energi som kan fjernes fra timen; nominell effekt eller momentan sum er ikke et løfte om en hel times bidrag.

## Sammenhengen med blueprintene

Enkel lastkutt og climate-blueprinten leser kuttanbefalingen; prioritert lastkutt leser risiko. Varsel-blueprinten foreslår den største målte lasten som teller nå. Egne automasjoner kan kreve målt tilgjengelig effekt:

```yaml
condition:
  - condition: state
    entity_id: binary_sensor.effektvakt_kutt_ned_anbefalt
    state: "on"
  - condition: numeric_state
    entity_id: sensor.effektvakt_tilgjengelig_kutt
    above: 0.5
```

Her må tilgjengelig kutt være strengt over 0,5 kW.

## Fra strategier til laster

Oppsett før entry-versjon 2 migreres automatisk: beredersensor får terskel 1 000 W, ekstra sensorer 100 W. Aktuatorer kunne ikke migreres; koble dem til under Konfigurer.

## Lastprofiler

Historikk eller manuell profil anslår bidraget over tid. En manuell profil uten wattmåling brukes bare til planlegging. Maks kuttvarighet i profilen må passe lastens grenser og blueprinten. Se [lastprofiler](lastprofiler.md).
