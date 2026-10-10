# Savings potential and load profiles

[Norsk](sparepotensial.md)

## The BKK calculation

The historical monthly top-three averages were 5.823 kW in December 2025 and 5.702 kW in February 2026. At NOK 415 per month above 5 kW and NOK 250 at or below 5 kW, lowering both averages by 1 kW gives 4.823 and 4.702 kW and saves NOK 165 each: NOK 330 in total. Lowering them by 600 W gives 5.223 and 5.102 kW, which remain in the same tier. The underlying readings are described in the [fixture documentation](../tests/fixtures/README.md).

## A monthly target

The development version adds **Monthly target** under **Configure**. Choose a capacity tier from your grid company's table, such as 5 kW. Effektvakt then protects that target from the start of the month. This can trigger earlier and more frequent reductions than the default setting, even before the current hour can lock in a higher charge. It means accepting deferred consumption to leave room for the rest of the month.

The target does not change the calculation of billed capacity charges. Recorded daily maxima determine whether the target remains achievable. Once three recorded daily maxima average above the target, its status becomes `tapt` (lost), and Effektvakt resumes its usual assessment of which higher tier can still be avoided. The setting remains saved and is tried again next month. Choose **Off** to use the default assessment throughout.

`maal_kutt_anbefalt` indicates that a reduction can limit a new daily maximum above the target ceiling. It does not promise to recover the whole hour or save a particular amount of money. `timen_flytter_trinnet` and the cost attributes continue to describe the current effect on the capacity tier. Keep the maximum off-time and minimum on-time configured in your blueprints.

## What a load can contribute

A 600 W load that would otherwise run for the entire hour contributes 0.6 kWh. Running for only ten minutes contributes 0.1 kWh. The difference in energy over the whole clock hour determines the reduction in its average power. Current power alone cannot establish that benefit.

`scripts/analyser_lastprofil.py` analyses timestamped watt readings from a local JSON file. It reports time-weighted active share, active power, energy, coverage and observed cycle lengths. Selected peak windows can be analysed separately. A 500 W load active for a quarter of the time averages 125 W; this does not promise 125 W of available reduction in the next peak hour.

Remaining duration is estimated from complete observed cycles that lasted at least as long as the current active period. The report includes the number of supporting cycles. Cycles crossing a window boundary or a data gap are incomplete and excluded from that estimate. This can still bias the sample towards shorter cycles. Unknown power is never treated as zero. Readings are held until the next report unless you choose a maximum hold time; high coverage does not establish that a sensor is fresh or accurate.

A thermostat in `heat` mode does not establish actual heating. Without watt readings, active share cannot be calculated. Multiple sensors for one load must be resolved before summing them, especially when they disagree. Lights can help with a small excess near a tier boundary. Floor heating and hot water need temperature, comfort and subsequent reheating considered together. The local analysis tool does not switch loads. The development version can use profiles from measured active loads in its reduction assessment when the optional profile setting is enabled; see [profiles in Home Assistant](lastprofiler.en.md#profiles-inside-home-assistant).

## Arithmetic example and simulated control

The [README example](../README.en.md#a-savings-example-from-bkk) shows a potential 330 NOK reduction in capacity charges if the monthly top-three averages in December 2025 and February 2026 were actually reduced by 1 kW. It assumes ideal reductions throughout the relevant hours.

`scripts/simuler_sparing.py` instead makes decisions during historical hours without knowing future peaks. Hourly consumption is represented as constant power within each hour, with a hypothetical flexible load available within the household's consumption. Deferred energy is returned using a chosen power, maximum off-time and minimum on-time. This models shifting consumption; it is not a temperature model or a measurement of actual savings.

With 600 W and 1 kW, using either the default assessment or a selected 5 kW target, this model reduced no capacity charges across complete months when deferred energy was returned immediately at the same power. Some monthly top-three averages increased without changing the billed tier. January 2026 is missing 105 hours and is excluded from the aggregate comparison. The result shows why restoration and the timing of subsequent consumption matter alongside the initial reduction. It does not establish that real control has no benefit.

Run from the repository root:

```bash
uv run --group unit python scripts/simuler_sparing.py
uv run --group unit python scripts/analyser_lastprofil.py profile.json --start 2026-01-01T00:00:00+01:00 --slutt 2026-01-08T00:00:00+01:00 --terskel-w 100
```

The load-profile script describes its input format in its help text. Keep personal measurement histories in local files. Establishing real savings requires measurements of available loads during peak hours, actual switching, restoration and subsequent consumption. Simulated potential is not reported as measured savings.

See the [load-profile method](lastprofiler.en.md) and the [example report](research/lastprofil-rapport.en.md) for observations and manual assumptions.
