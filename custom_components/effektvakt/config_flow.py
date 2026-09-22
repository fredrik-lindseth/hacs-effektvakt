"""Config flow for Effektvakt."""

from __future__ import annotations

import json
import logging
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
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


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


def _dso_options() -> list[selector.SelectOptionDict]:
    options = [
        selector.SelectOptionDict(value=k, label=v["navn"])
        for k, v in sorted(KAPASITETSTRINN_PER_DSO.items(), key=lambda kv: kv[1]["navn"])
    ]
    options.append(selector.SelectOptionDict(value="custom", label="Egendefinert"))
    return options


class EffektvaktConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

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
                return await self.async_step_tuning()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="power"),
                    ),
                    vol.Optional(CONF_ENERGY_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy"),
                    ),
                    vol.Optional(CONF_CONFIRM_PEAK_SENSOR, default=False): selector.BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_pricing(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                raw = json.loads(user_input[CONF_KAPASITETSTRINN_CUSTOM])
                if not isinstance(raw, list) or not raw:
                    raise ValueError
                normalized = []
                prev_kw = -1.0
                for entry in raw:
                    if not (isinstance(entry, list | tuple) and len(entry) == 2):
                        raise ValueError
                    kw, pris = float(entry[0]), int(entry[1])
                    if kw <= prev_kw:
                        raise ValueError
                    normalized.append((kw, pris))
                    prev_kw = kw
                self._data[CONF_KAPASITETSTRINN_CUSTOM] = normalized
                return await self.async_step_tuning()
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

    async def async_step_tuning(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=KAPASITETSTRINN_PER_DSO.get(self._data[CONF_DSO], {}).get("navn", "Effektvakt"),
                data=self._data,
            )

        return self.async_show_form(
            step_id="tuning",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SAFETY_BUFFER_KW, default=DEFAULT_SAFETY_BUFFER_KW): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1, max=5, step=0.1, mode=selector.NumberSelectorMode.SLIDER
                        ),
                    ),
                    vol.Required(
                        CONF_MIN_RISIKO_FOR_KUTT, default=DEFAULT_MIN_RISIKO_FOR_KUTT
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_risiko_valg(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_MIN_RISIKO_FOR_KUTT,
                        ),
                    ),
                    vol.Required(
                        CONF_RISIKO_HOLDETID_MINUTTER, default=DEFAULT_RISIKO_HOLDETID_MINUTTER
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=30, mode=selector.NumberSelectorMode.BOX),
                    ),
                    vol.Required(CONF_KUTT_STRATEGI, default=DEFAULT_KUTT_STRATEGI): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[selector.SelectOptionDict(value=s, label=s) for s in STRATEGI_OPTIONS],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="kutt_strategi",
                        ),
                    ),
                    vol.Optional(CONF_VVB_POWER_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="power"),
                    ),
                    vol.Optional(CONF_EKSTRA_POWER_SENSORS, default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="power",
                            multiple=True,
                        ),
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EffektvaktOptionsFlow(config_entry)


class EffektvaktOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            return self.async_create_entry(title="", data={})
        data = self.config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SAFETY_BUFFER_KW,
                        default=data.get(CONF_SAFETY_BUFFER_KW, DEFAULT_SAFETY_BUFFER_KW),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1, max=5, step=0.1, mode=selector.NumberSelectorMode.SLIDER
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
                        default=data.get(CONF_KUTT_STRATEGI, DEFAULT_KUTT_STRATEGI),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[selector.SelectOptionDict(value=s, label=s) for s in STRATEGI_OPTIONS],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="kutt_strategi",
                        ),
                    ),
                    vol.Optional(CONF_VVB_POWER_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="power"),
                    ),
                    vol.Optional(CONF_EKSTRA_POWER_SENSORS, default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="power",
                            multiple=True,
                        ),
                    ),
                }
            ),
        )
