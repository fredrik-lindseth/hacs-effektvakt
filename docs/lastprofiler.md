# Lastprofiler

En profil anslår påandel, aktiv effekt og restvarighet. Siste uke brukes som beste anslag for neste uke; vær, varmtvannsbehov og bruksmønster kan endre resultatet.

## Effekt, påandel og energi

2 000 W med 15 % arbeidssyklus gir 300 W i gjennomsnitt, eller 0,3 kWh per gjennomsnittstime. Momentant kutt kan være 2 kW når lasten varmer; energibidraget avhenger av hvor lenge den ellers ville fortsatt. Tell hver fysisk last én gang.

## Profiler inne i Home Assistant

Utviklingsversjonen har **Av**, **Historikk (siste sju dager)** og **Manuell** per last under Konfigurer.

| Valg | Grunnlag |
| --- | --- |
| Historikk | Effektsensor i recorder; oppdateres ved oppstart og hver time. Egne kutt holdes utenfor læringen. |
| Manuell | Nominell W og arbeidssyklus; typisk påtid er valgfri. Uten måling er profilen bare et planleggingsanslag. |

Recorder-feil beholder siste profil med feilstatus. Profiler eldre enn 24 timer brukes ikke. Aktuatormodus `heat` regnes ikke som målt oppvarming.

Maks kuttvarighet begrenser estimatet, men erstatter ikke blueprintens frist. Sett grensene etter lasten. Estimatsensoren viser kWh; tilgjengelig kutt viser fortsatt målte kW. [Sensorfelter](sensorer.md#lastprofiler-og-estimert-kuttenergi).

**Bruk lastprofiler i kuttvurderingen** er av som standard. På bruker energi fra målte aktive laster; laster uten profil beholder antakelsen om drift resten av timen. Manuelle profiler uten måling gir ingen automatisk kuttkapasitet. Valg av enkeltlaster og gjenoppvarmingsplanlegging gjenstår.

## Kjør analysen selv

Analyseverktøyet trenger Python 3.11+, uten HA. Kunstig `profil.json` med én hel påperiode på tjue minutter:

```json
{
  "punkter": [
    {"tid": "2026-01-01T00:00:00+01:00", "watt": 0},
    {"tid": "2026-01-01T00:10:00+01:00", "watt": 300},
    {"tid": "2026-01-01T00:30:00+01:00", "watt": 0},
    {"tid": "2026-01-01T01:00:00+01:00", "watt": null}
  ],
  "vinduer": [["2026-01-01T00:00:00+01:00", "2026-01-01T01:00:00+01:00"]]
}
```

```bash
uv run --group unit python scripts/analyser_lastprofil.py profil.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-01T01:00:00+01:00 --terskel-w 100 --allerede-paa-minutter 10 --minst-videre-minutter 5 > rapport.json
```

Resultatet er 100 Wh, 33,3 % påandel, 300 W aktiveffekt og én hel syklus. Etter ti minutters påtid finnes én støttende syklus for restvarighet. Valgfrie `vinduer` kan angi husets faktiske topptimer.

## Eksporter historikken fra Home Assistant

Lag et langvarig tilgangstoken i HA-profilen. Erstatt adresse, sensor og tidsrom; verktøyet spør etter token uten å vise det eller lagre det i shell-historikken.

```bash
uv run --group unit python scripts/hent_lastprofil.py --url https://ha.example --sensor sensor.example_power --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --utfil profil.json
uv run --group unit python scripts/analyser_lastprofil.py profil.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --terskel-w 100 > rapport.json
```

Eksporten bruker `/api/history/period`, tar med initialtilstand og normaliserer W/kW til W. Bare `tid` og `watt` lagres, uten token, navn eller entitets-ID. Oppbevar råhistorikken lokalt.

`HA_URL` og `HA_TOKEN` kan komme fra miljøet; token godtas ikke som kommandolinjeargument. Timeout er standard 60 sekunder. Omdirigering avvises. Tom historikk kan skyldes recorder-ekskludering, slettede data eller manglende tilgang.

## Slik regner verktøyet

Tilstand gjelder fram til neste endring; energi og påandel tidsvektes. Effekt strengt over terskelen er aktiv. Ukjente intervaller utelates fra kjent energi; dekning er kjent tid delt på målevinduet.

Høy dekning beviser ikke ferske målinger. `--maks-hold-sekunder 600` gjør en verdi ukjent etter ti minutter uten rapport; tilpass grensen til sensorens rapportering.

Bare hele påperioder brukes for restvarighet. Perioder over vindusgrensen eller med ukjent effekt utelates. Bare sykluser minst like lange som allerede kjent påtid støtter anslaget; antallet vises. Dette kan gi overvekt av korte sykluser. Tidspunkter må ha tidssone; varighet regnes i faktisk tid også ved sommertidsskifte.

## Bruk profilen til å spare

Sammenlign nødvendig energi ut av timen med aktive lasters anslag innen tillatt kuttvarighet. Behold komfort, frister og minste påtid. Riktig aktuator lar egne kutt holdes utenfor læringen. Utsatt energi må få plass senere; et lavere kapasitetstrinn kan spare kroner uten å spare kWh. [Simulering](sparepotensial.md#regneeksempel-og-simulert-styring) og [eksempelrapport](research/lastprofil-rapport.md).
