# Kutt-strategi

Strategien bestemmer hva `sensor.effektvakt_tilgjengelig_kutt` rapporterer. Den påvirker ikke risiko-vurderingen, som alltid baserer seg på projisert time-snitt mot trinnterskel.

---

## De tre strategiene

### blind

**Sensorer**: Ingen ekstra.

**Hva den gjør**: Returnerer alltid 0,3 kW, basert på at en norsk standard VVB (2 kW element) er aktiv ca. 15% av tiden i normal drift.

**Problem**: Duty cycle-antagelsen på 15% betyr at det er 85% sjanse for at VVB-en _ikke_ varmer i et gitt øyeblikk. Slår du av VVB blindt når timen ligger like under terskelen, er den reelle forventede effektreduksjonen 0,15 × 2 kW = 0,3 kW. Noen ganger er VVB aktiv og kuttet gir 2 kW. Noen ganger er den allerede av og kuttet gir 0 kW.

**Når bruke**: Ingen smart plugg på VVB. Rask oppsett. Akseptabelt for testing eller husholdninger der VVB sjelden er den avgjørende faktoren.

---

### vvb_status

**Sensorer**: En `vvb_power_sensor` (W eller kW).

**Hva den gjør**: Leser VVB-effekten i sanntid. Hvis VVB er aktiv (over 1 000 W terskel), rapporteres faktisk effekt (typisk ~2 kW). Hvis VVB er i pause, rapporteres 0,0 kW.

**Fordel**: Blueprints kan nå slå av VVB kun når elementet faktisk varmer. Forventet kutt per event er 1-2 kWh i stedet for 0,05-0,15 kWh.

**Eksempel-tall**: VVB er av halve timen (duty cycle 15%). I de 15% av minuttene der VVB varmer: faktisk kutt = 2,0 kW. I resten: `tilgjengelig_kutt` = 0,0 kW, blueprint gjør ingenting.

**Når bruke**: Du har en smart plugg med effektmåling på VVB. Anbefalt hvis VVB er primær kutt-kilde.

---

### vvb_pluss_ekstra

**Sensorer**: En `vvb_power_sensor` pluss en eller flere `ekstra_power_sensors`.

**Hva den gjør**: VVB-bidraget (som i `vvb_status`) pluss summen av alle ekstra-sensorer over 100 W terskel.

**Eksempel-tall fra typisk husholdning**:

| Last                | Effekt når aktiv | Bidrag til kutt |
| ------------------- | ---------------- | --------------- |
| VVB (OSO Saga 200L) | 2 000 W          | 2,0 kW          |
| Gulvvarme bad       | 550 W            | 0,55 kW         |
| Gulvvarme stue      | 900 W            | 0,90 kW         |
| Panelovn            | 1 200 W          | 1,2 kW          |
| **Sum**             |                  | **4,65 kW**     |

Med 4,65 kW tilgjengelig kutt er det god margin mot de fleste trinngrenser. Blueprints kan bruke `sensor.effektvakt_tilgjengelig_kutt` for å avgjøre hvilke laster som faktisk er nødvendig å skru av.

**Når bruke**: Du har effektmåling på flere laster og vil ha presist bilde av total kuttkapasitet.

---

## Sammenligning

|                 | blind                       | vvb_status | vvb_pluss_ekstra      |
| --------------- | --------------------------- | ---------- | --------------------- |
| Ekstra sensorer | Nei                         | VVB        | VVB + liste           |
| Presisjon       | Lav                         | God        | Best                  |
| Oppsett         | Enkelt                      | Middels    | Mer arbeid            |
| Anbefalt for    | Testing / ingen smart plugg | VVB alene  | Flere kuttbare laster |

---

## Hva som utgjør tallet

`sensor.effektvakt_tilgjengelig_kutt` har attributtet `kutt_kilder` med én oppføring per konfigurert kilde, så et dashboard kan vise hva som faktisk er kuttbart akkurat nå framfor bare summen. Feltene er dokumentert i [sensorer.md](sensorer.md#kutt_kilder).

Strategien avgjør hvem som teller:

| Strategi           | VVB teller | Ekstra teller |
| ------------------ | ---------- | ------------- |
| `blind`            | Nei        | Nei           |
| `vvb_status`       | Ja         | Nei           |
| `vvb_pluss_ekstra` | Ja         | Ja            |

Kilder som er konfigurert, men ikke teller i gjeldende strategi, er med i lista med `teller_med: false`. Bytter du fra `vvb_pluss_ekstra` til `vvb_status`, blir ekstra-sensorene altså stående, bare uten å bidra. Det samme gjelder en kilde som ligger under terskelen for rollen sin, eller en sensor som er `unavailable`: den siste får `effekt_w: null`, siden vi da ikke vet hva lasten trekker.

Med `blind` teller ingen kilder, og tilstanden er duty cycle-antagelsen på 0,3 kW. For de to andre strategiene er tilstanden summen av `effekt_w` for kildene med `teller_med: true`.

---

## Effekt på blueprints

`sensor.effektvakt_tilgjengelig_kutt` er primært en informasjons-sensor og en hjelpe-sensor for dashboards. De medfølgende blueprints bruker `binary_sensor.effektvakt_kutt_ned_anbefalt` som trigger, ikke `tilgjengelig_kutt` direkte.

Hvis du vil lage automations som bare slår av en last når kutt-kapasiteten faktisk er tilgjengelig, kan du kombinere:

```yaml
condition:
  - condition: state
    entity_id: binary_sensor.effektvakt_kutt_ned_anbefalt
    state: "on"
  - condition: numeric_state
    entity_id: sensor.effektvakt_tilgjengelig_kutt
    above: 0.5
```

Dette slår bare av lasten hvis Effektvakt anbefaler kutt _og_ vi faktisk har minst 0,5 kW tilgjengelig (dvs. VVB-en varmer).
