# Example load-profile report

[Norsk](lastprofil-rapport.md)

This report uses synthetic data from the [method's sample file](../lastprofiler.en.md#run-the-analysis-yourself). It shows how to document an analysis without publishing raw history. Its numbers describe no particular household.

## Window and evidence

The window is 1 January 2026, 00:00–01:00 Norwegian winter time. The load draws 0 W for ten minutes, 300 W for twenty minutes, then 0 W for thirty minutes. The threshold is 100 W. States are held until the next recorded change; no unknown intervals fall inside the window.

| Result | Value |
| --- | ---: |
| Known time | 60 minutes |
| Active time | 20 minutes |
| State coverage | 100% |
| Duty cycle | 33.3% |
| Active power | 300 W |
| Time-weighted mean | 100 W |
| Energy | 0.100 kWh |
| Complete active periods | 1 |

After ten active minutes, the only comparable cycle has ten minutes remaining. One case supports the remaining-duration estimate. Assuming twenty more minutes would exceed the evidence in this example.

## Use the numbers

If the load would otherwise run for ten more minutes, switching it off contributes 300 W × 10/60 hour = 0.050 kWh, reducing the hourly average by 50 W. Instantaneous power is 300 W, but the profile describes a smaller contribution across the clock hour.

As a separate manual scenario, 2,000 W of combined floor heating plus 300 W in another zone at an assumed 15% duty cycle averages 345 W. This assumption does not establish which zones heat simultaneously. Count each zone once and assess bathroom heating or other loads separately.

## Document your own household

Record the window, time zone, threshold, known coverage and whether states were carried forward. Distinguish measured values from manually entered rated power and assumed duty cycle. Include the number of complete cycles supporting remaining-duration estimates. Compare actual peak hours instead of using daily averages alone.

When several sensors describe one physical load, check units, switch state and freshness before summing. A controlled on/off observation can reveal channels holding stale power or reporting zero. High state coverage alone does not establish accuracy. Report unresolved channels as unresolved evidence.

A savings report should describe switching and restoration, including where deferred energy went. The [BKK example and simulation](../sparepotensial.en.md#arithmetic-example-and-simulated-control) compare ideal reductions with a model that returns the energy. Multiplying current active power by the remaining hour does not establish saved grid charges.

Keep personal raw history and actual household profiles locally. Choose deliberately what to share in a public report.
