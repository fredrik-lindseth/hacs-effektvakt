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
    CONF_ENERGY_SENSOR,
    CONF_KAPASITETSTRINN_CUSTOM,
    CONF_LAST_BRYTER,
    CONF_LAST_EFFEKT_SENSOR,
    CONF_LAST_NAVN,
    CONF_LAST_TERSKEL_W,
    CONF_LASTER,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    DEFAULT_DSO,
    DEFAULT_LAST_TERSKEL_W,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    ENTRY_VERSION,
    LEGACY_RISIKO_MAPPING,
    MAX_LAST_TERSKEL_W,
    PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS,
    PEAK_SENSOR_NAME_PATTERNS,
    RISIKO_GOD_MARGIN,
    RISIKO_LEVELS,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
)
from .dso import KAPASITETSTRINN_PER_DSO
from .laster import LastOppsett, last_til_lagring, les_laster

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)

# Feltet i skjemaet for en last som betyr «fjern denne». Det ligger ikke i
# const.py fordi det aldri lagres: det er et svar i en dialog, ikke et
# konfigurasjonsfelt.
CONF_SLETT_LAST = "slett"


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
        }
    )


def last_skjema(last: Mapping[str, Any] | None = None, *, kan_slettes: bool = False) -> vol.Schema:
    """Skjemaet for en enkelt kuttbar last.

    Navnet er valgfritt. Står det tomt, bruker integrasjonen sensorens eget
    friendly_name, og da heter lasten det samme her som ellers i Home
    Assistant. Terskelen er per last fordi lastene er ulike: et berederelement
    er enten fullt på eller av og hører hjemme rundt 1000 W, mens varmekabler
    på 550 W aldri ville kommet over den terskelen.
    """
    lagret = last or {}
    felter: dict[Any, Any] = {
        vol.Required(
            CONF_LAST_EFFEKT_SENSOR,
            description={"suggested_value": lagret.get(CONF_LAST_EFFEKT_SENSOR)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power"),
        ),
        vol.Optional(
            CONF_LAST_NAVN,
            description={"suggested_value": lagret.get(CONF_LAST_NAVN)},
        ): selector.TextSelector(),
        vol.Optional(
            CONF_LAST_BRYTER,
            description={"suggested_value": lagret.get(CONF_LAST_BRYTER)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "input_boolean"]),
        ),
        vol.Required(
            CONF_LAST_TERSKEL_W,
            default=float(lagret.get(CONF_LAST_TERSKEL_W, DEFAULT_LAST_TERSKEL_W)),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=MAX_LAST_TERSKEL_W,
                step=10,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="W",
            ),
        ),
    }
    if kan_slettes:
        felter[vol.Optional(CONF_SLETT_LAST, default=False)] = selector.BooleanSelector()
    return vol.Schema(felter)


def valider_last(
    svar: Mapping[str, Any],
    *,
    lagrede: list[LastOppsett],
    erstatter: str | None = None,
) -> tuple[LastOppsett | None, dict[str, str]]:
    """Svaret fra lastskjemaet som `LastOppsett`, eller feilene som stoppet det.

    Rent, uten `hass`: enhetsvalideringen av sensoren gjøres av kalleren, som
    har tilstandsmaskinen. Her står bare det som kan avgjøres av svaret og de
    lagrede lastene, altså at to laster ikke deler effektsensor. Delte de den,
    ville `tilgjengelig_kutt` talt den samme effekten to ganger, og
    kuttsporingen hatt to laster med samme nøkkel.
    """
    sensor = str(svar[CONF_LAST_EFFEKT_SENSOR])
    opptatt = {last.effekt_sensor for last in lagrede if last.effekt_sensor != erstatter}
    if sensor in opptatt:
        return None, {CONF_LAST_EFFEKT_SENSOR: "last_finnes_allerede"}

    navn = str(svar.get(CONF_LAST_NAVN) or "").strip()
    bryter = str(svar.get(CONF_LAST_BRYTER) or "").strip()
    return (
        LastOppsett(
            effekt_sensor=sensor,
            navn=navn or None,
            bryter=bryter or None,
            terskel_w=float(svar.get(CONF_LAST_TERSKEL_W, DEFAULT_LAST_TERSKEL_W)),
        ),
        {},
    )


def _last_valg(laster: list[LastOppsett]) -> list[selector.SelectOptionDict]:
    """Lastene som en dropdown, med effektsensoren som verdi.

    Sensoren og ikke indeksen er verdien: en indeks ville pekt på feil last i
    det noen fjernet en annen i et annet nettleservindu.
    """
    return [
        selector.SelectOptionDict(value=last.effekt_sensor, label=last.navn or last.effekt_sensor) for last in laster
    ]


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
    return {**lagret, **user_input}


class EffektvaktConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    VERSION = ENTRY_VERSION

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
    """Configure-dialogen. `self.config_entry` kommer fra HA, se over.

    Dialogen aapner paa en meny framfor et skjema, fordi de kuttbare lastene er
    en liste og en liste ikke kan redigeres i ett skjema. Hvert valg skriver
    til config entryen med en gang og kommer tilbake til menyen, saa ingenting
    gaar tapt om brukeren lukker dialogen uten aa gaa veien ut.
    """

    def __init__(self) -> None:
        self._rediger: str | None = None

    @property
    def _laster(self) -> list[LastOppsett]:
        return les_laster(self.config_entry.data.get(CONF_LASTER))

    def _skriv(self, data: dict[str, Any]) -> None:
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)

    def _skriv_laster(self, laster: list[LastOppsett]) -> None:
        ny = dict(self.config_entry.data)
        if laster:
            ny[CONF_LASTER] = [last_til_lagring(last) for last in laster]
        else:
            ny.pop(CONF_LASTER, None)
        self._skriv(ny)

    def _sensorfeil(self, entity_id: str) -> dict[str, str]:
        """Effektsensoren for en last, maalt mot tilstandsmaskinen."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return {CONF_LAST_EFFEKT_SENSOR: "sensor_not_found"}
        if (state.attributes or {}).get("unit_of_measurement") not in VALID_POWER_UNITS:
            return {CONF_LAST_EFFEKT_SENSOR: "power_unit_invalid"}
        return {}

    async def async_step_init(self, _user_input: dict[str, Any] | None = None) -> FlowResult:
        valg = ["innstillinger", "legg_til_last"]
        if self._laster:
            valg.append("velg_last")
        valg.append("ferdig")
        return self.async_show_menu(step_id="init", menu_options=valg)

    async def async_step_innstillinger(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._skriv(flettet_data(self.config_entry.data, user_input))
            return await self.async_step_init()
        return self.async_show_form(
            step_id="innstillinger",
            data_schema=innstillinger_skjema(self.config_entry.data),
        )

    async def async_step_legg_til_last(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._sensorfeil(user_input[CONF_LAST_EFFEKT_SENSOR])
            if not errors:
                last, errors = valider_last(user_input, lagrede=self._laster)
                if last is not None:
                    self._skriv_laster([*self._laster, last])
                    return await self.async_step_init()
        return self.async_show_form(
            step_id="legg_til_last",
            data_schema=last_skjema(user_input),
            errors=errors,
        )

    async def async_step_velg_last(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        laster = self._laster
        if user_input is not None:
            self._rediger = str(user_input[CONF_LAST_EFFEKT_SENSOR])
            return await self.async_step_rediger_last()
        return self.async_show_form(
            step_id="velg_last",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LAST_EFFEKT_SENSOR): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_last_valg(laster),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
        )

    async def async_step_rediger_last(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        laster = self._laster
        valgt = next((last for last in laster if last.effekt_sensor == self._rediger), None)
        if valgt is None:
            return await self.async_step_init()

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_SLETT_LAST):
                self._skriv_laster([last for last in laster if last.effekt_sensor != valgt.effekt_sensor])
                return await self.async_step_init()
            errors = self._sensorfeil(user_input[CONF_LAST_EFFEKT_SENSOR])
            if not errors:
                ny, errors = valider_last(user_input, lagrede=laster, erstatter=valgt.effekt_sensor)
                if ny is not None:
                    self._skriv_laster([ny if last is valgt else last for last in laster])
                    return await self.async_step_init()

        return self.async_show_form(
            step_id="rediger_last",
            data_schema=last_skjema(user_input or last_til_lagring(valgt), kan_slettes=True),
            errors=errors,
            description_placeholders={"navn": valgt.navn or valgt.effekt_sensor},
        )

    async def async_step_ferdig(self, _user_input: dict[str, Any] | None = None) -> FlowResult:
        """Lukk dialogen. Alt er alt skrevet, saa her lages bare en tom entry."""
        return self.async_create_entry(title="", data={})
