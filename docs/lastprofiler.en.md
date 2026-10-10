# Load profiles

[Norsk](lastprofiler.md)

A load profile describes how often a load draws power, its power while active and how long it tends to continue. We use the previous week as our best estimate for the next week and update it with newer observations. This helps choose a reduction that contributes enough within the hour while limiting disruption.

## Power, active share and energy

2,000 W of heating with a 15% duty cycle averages 300 W over time, or 0.3 kWh per average hour. When the heating is running, instantaneous available reduction can be 2 kW. Its contribution to the hour depends on how long it would otherwise continue and how long it may remain switched off.

300 W that would otherwise run for twenty minutes contributes 0.1 kWh. If the thermostat would stop after five minutes, the contribution is 0.025 kWh. When the elapsed active time is known, comparable historical cycles help estimate remaining operation instead of assuming a full remaining hour.

Measured power, assumed rated power and a profile-based energy estimate have different evidence behind them. A manual duty cycle can be useful when this week's readings are unrepresentative, but must be shown as an assumption. Count each physical appliance once.

Profiles update hourly. A temporary recorder failure retains the last profile with its original update time and error status. Profiles older than 24 hours are excluded from reduction-energy estimates and control advice; their historical basis remains visible. A manual profile without a measurement provides planning estimates and does not create the measured available-reduction sensor.

## Profiles inside Home Assistant

The development version adds a profile setting to each controllable load under Configure. Choose **Off**, **History (last seven days)** or **Manual**. Automatic profiles use the last seven days of recorder history and refresh in the background each hour. The power sensor must be included in recorder history.

For a manual profile, enter rated power in W and duty cycle in percent. Typical active duration is optional. A named manual load can be configured without a power sensor, for example for floor heating with known rated power. It contributes an estimate for planning and is not counted as measured instantaneous reduction. Climate entities may be associated as control actuators; `heat` mode is never interpreted as measured active heating.

Set maximum reduction duration to match the load's allowable off-time and its blueprint's limit; the profile default is sixty minutes. This setting bounds the estimate and does not replace the load guard's restoration deadline.

`sensor.effektvakt_estimert_kuttenergi_resten_av_timen` reports estimated reduction energy in kWh and is created when at least one load has a profile enabled. `sensor.effektvakt_tilgjengelig_kutt` continues to report measured power in kW. Per-load attributes identify the profile source, evidence, coverage, active power and supporting cycles. Unknown evidence is kept separate from zero contribution.

**Use load profiles in reduction assessment** is off by default. Enable it to use estimated energy from measured, currently active loads when assessing whether a reduction can help. Loads without a profile retain the existing assumption of availability throughout the remaining hour. Manual profiles without power measurement remain planning estimates and never provide automatic control capacity. Automatic selection of individual loads and scheduling their reheating remain separate work.

## Run the analysis yourself

From the repository root, run the tool in the unit environment through `uv`, without Home Assistant. The analysis tool itself uses only the standard library and requires Python 3.11 or newer. Create a local `profile.json` with timestamps and power in W. This synthetic example has one complete twenty-minute active period:

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
uv run --group unit python scripts/analyser_lastprofil.py profile.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-01T01:00:00+01:00 --terskel-w 100 --allerede-paa-minutter 10 --minst-videre-minutter 5 > report.json
```

The report shows 100 Wh, a 33.3% active share, 300 W of active power and one complete cycle. Only that one cycle supports the remaining-duration estimate. The optional `vinduer` field accepts actual household peak hours, so activity within those hours can be compared with activity across the whole period.

Retrieve your power sensor's history from Home Assistant and convert states to this format. Include the state valid at the start and all subsequent changes through the end. Multiply kW by 1,000 to normalise to W. Use `null` for `unknown`, `unavailable` and unreadable values. Timestamps must include a time zone. Keep personal raw data local; shared reports should omit entity identifiers and household details.

## Export your Home Assistant history

Create a long-lived access token in your Home Assistant user profile. Run the exporter locally; replace the URL, sensor and dates with your own. It prompts for the token without displaying it or writing it into shell history:

```bash
uv run --group unit python scripts/hent_lastprofil.py --url https://ha.example --sensor sensor.example_power --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --utfil profile.json
uv run --group unit python scripts/analyser_lastprofil.py profile.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --terskel-w 100 > report.json
```

The exporter uses HA's `/api/history/period` endpoint, requesting the selected sensor, the initial state and full attributes. It converts W and kW to W and retains unknown or invalid readings as `null`. Timestamps use UTC. Only `tid` and `watt` are written to the file; entity identifiers, friendly names and the token are excluded. Keep the file local because the power history itself can reveal household routines.

`HA_URL` can supply the URL instead of `--url`. For noninteractive use, supply `HA_TOKEN` from your existing secret environment; no token command-line option is supported. `--timeout` defaults to sixty seconds. Redirects are rejected, so use the final HA address. No history can mean the sensor is excluded from recorder, old data was purged or the token lacks read access. The exporter cannot restore missing readings.

## How the calculation works

Each recorded state is held until the next recorded change. Energy and active share are weighted by elapsed time, rather than sample count. Power must be strictly above the selected threshold to count as active. Choose a threshold above standby but below normal active power.

Unknown intervals are excluded from known energy and active share. `dekning` is known time divided by the full window duration. Sparse state changes can produce high coverage because values are held; this does not establish freshness. Use `--maks-hold-sekunder 600` to make a reading unknown after ten minutes without another report. Choose a limit that fits that sensor's reporting behaviour; a change-only sensor needs a different assessment from one reporting every minute.

An active period that began before the window, continues beyond it or is interrupted by unknown power has an unknown full duration. It contributes to known activity but is excluded from remaining-duration estimation. Only complete cycles at least as long as the current elapsed active period support the estimate. The report includes their count. Excluding incomplete cycles can overrepresent short cycles, especially with short windows.

Durations use elapsed time with time zones. During the autumn daylight-saving transition, the two local 02:00 hours are separate hours. Use timestamped windows corresponding to your meter's clock hours when analysing peaks.

## Use the profile to save money

Start with the energy that must be removed from the hour to protect a monthly target or avoid a higher tier. Compare it with each load's expected contribution within its allowed off-time. Current power and expected remaining active time matter more than daily averages when selecting a reduction.

Profiles should describe natural operation. Exclude periods when Effektvakt controlled the load; otherwise a controlled interruption can be learned as a natural thermostat stop. Associate the load with the actuator used for control and retain temperature limits, maximum off-time and minimum on-time.

Deferred heating or charging must be recovered without creating another peak. A lower capacity tier saves grid charges; shifting consumption does not itself save energy. The [simulation](sparepotensial.en.md#arithmetic-example-and-simulated-control) and [measurement report](research/lastprofil-rapport.en.md) explain why both must be assessed. The analysis tool does not switch loads.
