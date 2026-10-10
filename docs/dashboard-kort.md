# Effektvakt-kortet

Kortet følger med integrasjonen og finnes i Home Assistants kortvelger. Etiketter og editor følger HA-språket på norsk og engelsk.

## Legg det inn

Velg Effektvakt i kortvelgeren, eller bruk YAML:

```yaml
type: custom:effektvakt-card
entity: sensor.effektvakt_projisert_time_snitt
tittel: Effektvakt
```

Bruk din egen entitets-ID hvis den er omdøpt. For dashbordet fra README: lim inn [dashboard-eksempel.yaml](dashboard-eksempel.yaml) i et nytt dashbord via «Rediger i YAML». Bytt `BYTT_MEG` til din kumulative energisensor, og tilpass Effektvakt-entitetene ved behov.

## Hva viser kortet?

| Merke | Betydning |
| --- | --- |
| Tykk rød viser | Projisert timegjennomsnitt hvis forbruket fortsetter som nå. |
| Tynn svart viser | Effekten akkurat nå. |
| Trekant utenfor buen | Høyeste topp-3-snitt kortet har sett denne måneden. |
| Ytre bånd | Kapasitetstrinn og månedspris. Forventet trinn er tykt, neste trinn rødt. |
| `---` | Ingen gyldig måling. Viserne parkeres på null; meldingen under forklarer hvorfor. |

Trekanten nullstilles ved månedsskiftet og huskes per entitet og nettleser. En ny nettleser starter med sensorens verdi. En lav rød viser senker ikke allerede registrerte månedstopper.

De faste instrumentmerkene er dekor fra originalskivene. De beskriver ikke nøyaktigheten eller funksjonene til Effektvakt.

## Kortvalg

Valgene finnes også i den visuelle editoren.

| Nøkkel | Betydning |
| --- | --- |
| `entity` | Påkrevd: sensoren for projisert timegjennomsnitt. |
| `kostnad_entity` | Valgfri kostnadssensor; finnes automatisk på samme enhet. |
| `maks_kw` | Skalatopp, standard 15 kW. Rundes opp til en lesbar skalatopp. |
| `stil` | `geha` (lineær, standard) eller `gossen` (komprimert mot toppen). |
| `tittel` | Valgfri overskrift. |

## Ressurser i YAML-modus

Vanligvis registreres kortressursen automatisk. Bruker du Lovelace-ressurser i `configuration.yaml`, legg den inn selv:

```yaml
lovelace:
  resources:
    - url: /effektvakt-static/effektvakt-card.js?v=0.4.0
      type: module
```

Sett `v` til installert versjon fra `manifest.json`, og oppdater ved oppgradering.

## Feilsøking

| Problem | Sjekk |
| --- | --- |
| Kortet mangler eller viser «Konfigurasjonsfeil» | Se Innstillinger → Dashbord → Ressurser og YAML-oppsettet over. Last siden på nytt uten cache. |
| «Fikk ikke hentet skiven» | Kontroller `entity` og integrasjonens oppstartslogg. Kortet prøver igjen automatisk. |
| Ingen trinn er merket | Kontroller kostnadssensoren, eller sett `kostnad_entity` eksplisitt. |
| Trekanten står for høyt | Den husker maksimum. Nullstilles ved månedsskiftet; kan også slettes fra nettleserens `localStorage`. |

Utvikling og prøvebenk står i [utviklerguiden](development.md#prøve-lovelace-kortet).
