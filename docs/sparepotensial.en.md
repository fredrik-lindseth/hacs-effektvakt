# Savings potential and load profiles

[Norsk](sparepotensial.md)

## The BKK calculation

The historical monthly top-three averages were 5.823 kW in December 2025 and 5.702 kW in February 2026. At NOK 415 per month above 5 kW and NOK 250 at or below 5 kW, lowering both averages by 1 kW gives 4.823 and 4.702 kW and saves NOK 165 each: NOK 330 in total. Lowering them by 600 W gives 5.223 and 5.102 kW, which remain in the same tier. The underlying readings are described in the [fixture documentation](../tests/fixtures/README.md).

## A monthly target

In the development version, choose **Monthly target** under **Configure**, such as 5 kW. It is protected from the first day and can trigger earlier and more frequent reductions, even before the hour locks in a higher charge. **Off** uses the default assessment.

Once recorded daily maxima put the minimum achievable top-three average above the target, its status becomes `tapt` (lost) and the default assessment resumes. The choice remains saved for next month. `maal_kutt_anbefalt` describes contribution to the target; cost attributes still describe the tariff impact now. See the [sensor attributes](sensorer.md#valgt-månedsmål) and retain blueprint timing limits.

## What a load can contribute

600 W for one hour contributes 0.6 kWh; ten minutes contributes 0.1 kWh. Duration and subsequent reheating determine the hourly effect. [Load profiles](lastprofiler.en.md) describes measured power, duty cycle, remaining duration and use in HA.

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
