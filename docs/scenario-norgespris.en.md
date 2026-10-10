# Without Norgespris—or with a higher Norgespris

[Norsk](scenario-norgespris.md)

At 16,000 kWh annually, a 10 øre increase in Norgespris means **NOK 1,600 more per year**. Without Norgespris, the difference depends on prices when electricity is consumed, after Norway's electricity support.

## Identical consumption, different prices

This synthetic example assumes a spot contract, 25% VAT and consumption below 5,000 kWh every month. Consumption and timing stay identical. Grid charges, electricity taxes, the Enova levy and supplier markups/fixed fees are excluded from both alternatives. These are electricity supply costs, not complete bills or savings delivered by Effektvakt.

Norgespris is 50 øre/kWh including VAT through 2026. Without Norgespris, the 2026 support scheme covers 90% of each hourly price above 77 øre excluding VAT, equivalent to 96.25 øre including VAT. The schemes cannot be combined. [NVE's support rules](https://www.nve.no/reguleringsmyndigheten/kunde/stroem/dette-er-stroemstoetteordningen/), [government guidance on Norgespris and consumption caps](https://www.regjeringen.no/no/tema/energi/strom/sporsmal-og-svar-om-norgespris/id3089310/).

Each row assumes that spot price in **every hour**, not an annual average. Prices include VAT; 100 øre equals NOK 1. A positive difference means spot costs more than Norgespris at 50 øre.

| Spot (øre/kWh) | After support (øre/kWh) | Annual supply cost (NOK) | Difference from Norgespris at 50 øre (NOK/year) |
| ---: | ---: | ---: | ---: |
| 30 | 30 | 4,800 | −3,200 |
| 50 | 50 | 8,000 | 0 |
| 75 | 75 | 12,000 | +4,000 |
| 100 | 96.625 | 15,460 | +7,460 |
| 150 | 101.625 | 16,260 | +8,260 |
| 200 | 106.625 | 17,060 | +9,060 |

For an hourly spot price `P` in øre including VAT, the net price is `P − 0.90 × max(0, P − 96.25)`. Multiply by that hour's consumption and sum. Consuming half the electricity at 50 øre and half at 150 øre costs **NOK 12,130**, despite an average spot price of 100 øre. Applying support to the average would incorrectly give NOK 15,460.

## If Norgespris increases

| Norgespris including VAT | Annual supply cost | Increase from 50 øre |
| ---: | ---: | ---: |
| 50 øre/kWh | NOK 8,000 | NOK 0 |
| 60 øre/kWh | NOK 9,600 | NOK 1,600 |
| 70 øre/kWh | NOK 11,200 | NOK 3,200 |

60 and 70 øre are hypothetical inputs, not forecasts or stated 2027 rates. The government says the price changes from 2027; comparisons then must use the applicable rules. [Official price period](https://www.regjeringen.no/no/tema/energi/strom/sporsmal-og-svar-om-norgespris/id3089310/).

## What can Effektvakt change?

A lower capacity tier reduces grid charges under either scheme. Higher Norgespris increases the value of saved kWh, not the saving from a particular tier change. Deferred heating need not save energy. Within the consumption cap, shifting between spot-price hours does not change the Norgespris supply price; grid tariffs can still differ.

Without Norgespris, price scheduling must consider support. Effektvakt does not implement automatic spot-price scheduling. Billing and support calculations belong in Strømkalkulator. See [savings and simulation](sparepotensial.en.md).
