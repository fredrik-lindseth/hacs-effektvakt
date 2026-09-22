"""Config flow for Effektvakt."""

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CONFIRM_PEAK_SENSOR,
    CONF_DSO,
    CONF_EKSTRA_POWER_SENSORS,
    CONF_ENERGY_SENSOR,
    CONF_KAPASITETSTRINN_CUSTOM,
    CONF_KUTT_STRATEGI,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    CONF_VVB_POWER_SENSOR,
    DEFAULT_DSO,
    DEFAULT_KUTT_STRATEGI,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    LEGACY_RISIKO_MAPPING,
    LEGACY_STRATEGI_MAPPING,
    PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS,
    PEAK_SENSOR_NAME_PATTERNS,
    RISIKO_GOD_MARGIN,
    RISIKO_LEVELS,
    STRATEGI_OPTIONS,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
)
from .dso import KAPASITETSTRINN_PER_DSO

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)

# Felt uten default: er de borte fra svaret, har brukeren tømt dem, og da skal
# den lagrede verdien vekk i stedet for å overleve som et spøkelse.
TOEMBARE_FELT: tuple[str, ...] = (CONF_VVB_POWER_SENSOR,)


def looks_like_peak_sensor(entity_id: str, *, friendly_name: str = "") -> bool:
    """True hvis sensor-navn eller friendly_name antyder peak/snitt-aggregat."""
    lower_id = entity_id.lower()
    if any(pat in lower_id for pat in PEAK_SENSOR_NAME_PATTERNS):
        return True
    lower_name = friendly_name.lower()
    return any(kw in lower_name for kw in PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS)


def _risiko_valg() -> list[selector.SelectOptionDict]:
    """Nivåene brukeren kan velge som terskel for kutt.

    Laveste nivå er utelatt: «kutt allerede når marginen er god» er ikke et
    meningsfullt valg. Etikettene kommer fra selector-oversettelsen, så
    dropdownen leser likt som sensoren.
    """
    valgbare = [lvl for lvl in RISIKO_LEVELS if lvl != RISIKO_GOD_MARGIN]
    return [selector.SelectOptionDict(value=lvl, label=lvl) for lvl in valgbare]


def _lagret_risiko(verdi: str | None) -> str:
    """Nivået fra config entryen, oversatt fra de gamle verdiene om nødvendig."""
    if verdi is None:
        return DEFAULT_MIN_RISIKO_FOR_KUTT
    return LEGACY_RISIKO_MAPPING.get(verdi, verdi)


def _lagret_strategi(verdi: str | None) -> str:
    """Strategien fra config entryen, oversatt fra de gamle navnene.

    Samme grunn som `_lagret_risiko`: defaulten i dropdownen maa vaere et av
    valgene, ellers avviser Home Assistant sitt eget skjema naar brukeren
    trykker lagre. Coordinatoren oversetter alt gjennom
    LEGACY_STRATEGI_MAPPING, saa uten dette var dialogen det eneste stedet
    «vvb_billader» fortsatt var ugyldig.
    """
    if verdi is None:
        return DEFAULT_KUTT_STRATEGI
    return LEGACY_STRATEGI_MAPPING.get(verdi, verdi)


def _dso_options() -> list[selector.SelectOptionDict]:
    options = [
        selector.SelectOptionDict(value=k, label=v["navn"])
        for k, v in sorted(KAPASITETSTRINN_PER_DSO.items(), key=lambda kv: kv[1]["navn"])
    ]
    options.append(selector.SelectOptionDict(value="custom", label="Egendefinert"))
    return options


def sensor_skjema(forrige: Mapping[str, Any], *, vis_bekreftelse: bool) -> vol.Schema:
    """Sensorsteget, forhåndsutfylt med det brukeren alt har skrevet inn.

    Bekreftelsesboksen kommer først når peak-advarselen har slått til. Å be om
    en bekreftelse på en advarsel ingen har sett, er bare forvirrende.
    """
    felter: dict[Any, Any] = {
        vol.Required(
            CONF_POWER_SENSOR,
            description={"suggested_value": forrige.get(CONF_POWER_SENSOR)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power"),
        ),
        vol.Optional(
            CONF_ENERGY_SENSOR,
            description={"suggested_value": forrige.get(CONF_ENERGY_SENSOR)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy"),
        ),
    }
    if vis_bekreftelse:
        felter[vol.Optional(CONF_CONFIRM_PEAK_SENSOR, default=False)] = selector.BooleanSelector()
    return vol.Schema(felter)


def innstillinger_skjema(data: Mapping[str, Any]) -> vol.Schema:
    """Skjemaet i Configure, bygget over det som alt er lagret.

    Defaultene her er også det dialogen sender tilbake når brukeren bare
    trykker lagre. Henter de ikke lagret verdi, sletter en tur innom Configure
    det som stod der fra før.
    """
    return vol.Schema(
        {
            vol.Required(
                CONF_SAFETY_BUFFER_KW,
                default=data.get(CONF_SAFETY_BUFFER_KW, DEFAULT_SAFETY_BUFFER_KW),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.1,
                    max=5,
                    step=0.1,
                    mode=selector.NumberSelectorMode.SLIDER,
                ),
            ),
            vol.Required(
                CONF_MIN_RISIKO_FOR_KUTT,
                default=_lagret_risiko(data.get(CONF_MIN_RISIKO_FOR_KUTT)),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_risiko_valg(),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_MIN_RISIKO_FOR_KUTT,
                ),
            ),
            vol.Required(
                CONF_RISIKO_HOLDETID_MINUTTER,
                default=data.get(CONF_RISIKO_HOLDETID_MINUTTER, DEFAULT_RISIKO_HOLDETID_MINUTTER),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=30, mode=selector.NumberSelectorMode.BOX),
            ),
            vol.Required(
                CONF_KUTT_STRATEGI,
                default=_lagret_strategi(data.get(CONF_KUTT_STRATEGI)),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=s, label=s) for s in STRATEGI_OPTIONS],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="kutt_strategi",
                ),
            ),
            vol.Optional(
                CONF_VVB_POWER_SENSOR,
                description={"suggested_value": data.get(CONF_VVB_POWER_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power"),
            ),
            vol.Optional(
                CONF_EKSTRA_POWER_SENSORS,
                default=list(data.get(CONF_EKSTRA_POWER_SENSORS) or []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class="power",
                    multiple=True,
                ),
            ),
        }
    )


def parse_kapasitetstrinn(raa: str) -> list[tuple[float | None, int]]:
    """Egendefinerte trinn fra tekstfeltet, som `[kW, kr]`-par sortert stigende.

    `null` som terskel er det oeverste trinnet, det uten oevre grense, slik de
    innebygde tabellene slutter paa `(inf, pris)`. Uten den muligheten var alt
    over det hoeyeste tallet brukeren skrev prisfritt land: terskelen ble
    uendelig og risikoen `god_margin` for alltid, uten at noe sa fra.

    Uendelig lagres som `null` og ikke som `float("inf")`, fordi entry-data
    skal vaere gyldig JSON. `oppsett.les_trinn` oversetter tilbake.
    Sorteringskravet holder det aapne trinnet der det hoerer hjemme, sist.

    Kaster `ValueError` paa alt som ikke er en stigende liste av par.
    """
    raw = json.loads(raa)
    if not isinstance(raw, list) or not raw:
        raise ValueError("kapasitetstrinn maa vaere en ikke-tom liste")

    trinn: list[tuple[float | None, int]] = []
    forrige_kw = -1.0
    for rad in raw:
        if not (isinstance(rad, list | tuple) and len(rad) == 2):
            raise ValueError("hvert trinn maa vaere et [kW, kr]-par")
        terskel = None if rad[0] is None else float(rad[0])
        kw = math.inf if terskel is None else terskel
        if kw <= forrige_kw:
            raise ValueError("trinnene maa sorteres stigende, og bare det siste kan vaere null")
        trinn.append((terskel, int(rad[1])))
        forrige_kw = kw
    return trinn


def flettet_data(lagret: Mapping[str, Any], user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Lagret konfigurasjon med svarene fra Configure lagt over."""
    ny = {**lagret, **user_input}
    for noekkel in TOEMBARE_FELT:
        if noekkel not in user_input:
            ny.pop(noekkel, None)
    return ny


class EffektvaktConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._peak_advart = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DSO, default=DEFAULT_DSO): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_dso_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            power_id = user_input[CONF_POWER_SENSOR]
            energy_id = user_input.get(CONF_ENERGY_SENSOR)
            confirm_peak = user_input.get(CONF_CONFIRM_PEAK_SENSOR, False)

            power_state = self.hass.states.get(power_id)
            if power_state is None:
                errors[CONF_POWER_SENSOR] = "sensor_not_found"
            else:
                unit = (power_state.attributes or {}).get("unit_of_measurement")
                if unit not in VALID_POWER_UNITS:
                    errors[CONF_POWER_SENSOR] = "power_unit_invalid"
                else:
                    friendly = (power_state.attributes or {}).get("friendly_name", "")
                    if looks_like_peak_sensor(power_id, friendly_name=friendly) and not confirm_peak:
                        errors[CONF_POWER_SENSOR] = "peak_sensor_warning"
                        self._peak_advart = True

            if energy_id:
                e_state = self.hass.states.get(energy_id)
                if e_state is None:
                    errors[CONF_ENERGY_SENSOR] = "sensor_not_found"
                else:
                    e_unit = (e_state.attributes or {}).get("unit_of_measurement")
                    if e_unit not in VALID_ENERGY_UNITS:
                        errors[CONF_ENERGY_SENSOR] = "energy_unit_invalid"

            if not errors:
                unique_id = f"{DOMAIN}_{power_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                self._data.update(user_input)
                if self._data[CONF_DSO] == "custom":
                    return await self.async_step_pricing()
                return self._opprett_entry()

        return self.async_show_form(
            step_id="sensors",
            data_schema=sensor_skjema(user_input or {}, vis_bekreftelse=self._peak_advart),
            errors=errors,
        )

    async def async_step_pricing(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._data[CONF_KAPASITETSTRINN_CUSTOM] = parse_kapasitetstrinn(user_input[CONF_KAPASITETSTRINN_CUSTOM])
                return self._opprett_entry()
            except (ValueError, TypeError, json.JSONDecodeError):
                errors[CONF_KAPASITETSTRINN_CUSTOM] = "kapasitetstrinn_invalid"

        return self.async_show_form(
            step_id="pricing",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_KAPASITETSTRINN_CUSTOM): str,
                }
            ),
            errors=errors,
        )

    def _opprett_entry(self) -> FlowResult:
        """Siste steg i oppsettet: nettselskap og sensorer holder.

        Sikkerhetsmargin, holdetid, minste risikonivå og strategi spørres det
        ikke om her. Ingen kan svare på dem før integrasjonen har kjørt en uke,
        og defaultene gjelder til brukeren endrer dem under Configure.
        """
        dso = KAPASITETSTRINN_PER_DSO.get(self._data[CONF_DSO])
        return self.async_create_entry(
            title=dso["navn"] if dso else "Effektvakt",
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EffektvaktOptionsFlow:
        """Flyten bak Configure. Entryen sendes inn av HA, men skal ikke lagres.

        `OptionsFlow.config_entry` er en property uten setter fra HA 2025.12,
        og flytmotoren setter `handler` til entry_id-en rett etter at flyten er
        laget. Tar vi imot entryen her og setter den selv, kaster konstruktoeren
        og Configure-dialogen aapner ikke i det hele tatt.
        """
        return EffektvaktOptionsFlow()


class EffektvaktOptionsFlow(config_entries.OptionsFlow):
    """Configure-dialogen. `self.config_entry` kommer fra HA, se over."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_data = flettet_data(self.config_entry.data, user_input)
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=innstillinger_skjema(self.config_entry.data),
        )
