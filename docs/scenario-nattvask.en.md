# What can shifting laundry and dishes save?

[Norsk](scenario-nattvask.md)

With the assumed use below, moving all laundry and dishwashing from weekday daytime to BKK's lower-rate periods saves about NOK 88 per year in energy grid charges. Weekend daytime gives the same tariff benefit as nighttime.

## The calculation

BKK's rates from 1 January 2026 are 46.13 øre/kWh for daytime and 23.29 øre/kWh for nights/weekends, including taxes and VAT: a difference of 22.84 øre/kWh. Lower-rate periods are weekdays 22:00–06:00, all weekend and public holidays. [BKK tariff](https://www.bkk.no/en/grid-tariffs-for-private-customers), checked 10 October 2026.

Assume the following use. These are illustrative inputs, not measurements or typical values for every appliance:

| Appliance | Energy per cycle | Cycles per week | Annual kWh | Potential energy-grid-charge reduction |
| --- | ---: | ---: | ---: | ---: |
| Washing machine | 0.6 kWh | 4 | 124.8 | NOK 28.50 |
| Dishwasher | 1.0 kWh | 5 | 260.0 | NOK 59.38 |
| Total | | | 384.8 | NOK 87.89 |

```text
(0.6 × 4 + 1.0 × 5) × 52 weeks × NOK 0.2284/kWh = NOK 87.89/year
```

If half the energy is already used at the lower rate, remaining potential is about NOK 44/year. Use measured cycle energy and count only kWh actually moved between tariff periods. A cycle crossing 22:00 saves only on energy whose tariff changes.

## Other costs

For consumption covered by Norgespris, shifting time gives no additional electricity-price benefit; grid charges still vary. With a spot contract, electricity prices can add savings or losses. Compare prices after applicable electricity support, rather than raw spot prices. [NVE on Norgespris](https://www.nve.no/reguleringsmyndigheten/kunde/stroem/dette-er-norgespris/) and [electricity support](https://www.nve.no/reguleringsmyndigheten/kunde/stroem/dette-er-stroemstoetteordningen/).

Capacity charges depend on the month's three highest hourly averages from different days. Running both appliances alongside other nighttime loads may create new peaks. One higher BKK tier, from NOK 250 to NOK 415 for one month, costs NOK 165: more than the entire annual benefit above. A lower energy rate does not establish spare capacity. See the [calculation](beregninger.md#nve-modellen-for-kapasitetstrinn).

If you have solar panels, daytime may be a better option: generation used directly at home replaces purchased electricity and grid charges. Subtract the export income you give up before comparing with running appliances at night. The example above assumes grid purchases without solar generation. [NVE on self-consumption](https://www.nve.no/reguleringsmyndigheten/kunde/stroemnettet/prosumenter-og-plusskunder/).

## Use lower-rate periods while home and awake

DSB advises using washing machines and dishwashers while home and awake. Weekend daytime can provide the tariff benefit without running them while asleep. [DSB: safe and smart electricity control](https://www.dsb.no/sikkerhverdag/strom/trygg-og-smart-stromstyring/).

Effektvakt shows capacity and reduction needs but does not automatically schedule wash cycles. Shifting cycles saves cost without reducing energy in this example. See [savings potential](sparepotensial.en.md).
