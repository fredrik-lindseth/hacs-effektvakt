"""Servering av Effektvakt sitt eget Lovelace-kort.

Integrasjonen tar med seg kortet selv: filene under ``www/`` serveres paa
``/effektvakt-static``, og kort-URL-en meldes inn med ``add_extra_js_url`` slik
at Fredrik slipper aa registrere en Lovelace-ressurs for haand. Skiven hentes
over websocket i stedet for aa bli tegnet i JavaScript, saa kortet og trykkfilen
aldri kan drifte fra hverandre.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import (
    CONF_DSO,
    CONF_KAPASITETSTRINN_CUSTOM,
    DOMAIN,
    FRONTEND_CARD_FILENAME,
    FRONTEND_DIR_NAME,
    FRONTEND_URL_BASE,
    WS_TYPE_FACEPLATE,
)
from .dso import KAPASITETSTRINN_PER_DSO
from .faceplate import MAKS_KW_STANDARD, generate_faceplate, normaliser_maks_kw

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Registreringen hoerer til HA-oppstarten, ikke til en config entry. Flagget
# hindrer dobbeltregistrering hvis async_setup skulle bli kalt paa nytt:
# async_register_static_paths feiler paa en URL som alt er tatt.
DATA_FRONTEND_REGISTRERT: str = f"{DOMAIN}_frontend_registrert"

FRONTEND_DIR: Path = Path(__file__).parent / FRONTEND_DIR_NAME


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Server kortet, meld URL-en til frontend og aapne websocket-kommandoen."""
    if hass.data.get(DATA_FRONTEND_REGISTRERT):
        return
    hass.data[DATA_FRONTEND_REGISTRERT] = True

    await hass.http.async_register_static_paths([StaticPathConfig(FRONTEND_URL_BASE, str(FRONTEND_DIR), True)])

    # Cache-busteren maa henge paa: uten den serverer nettleseren forrige
    # versjon av kortet etter en oppdatering av integrasjonen.
    integration = await async_get_integration(hass, DOMAIN)
    versjon = str(integration.version) if integration.version else "0"
    frontend.add_extra_js_url(hass, f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={versjon}")

    websocket_api.async_register_command(hass, ws_faceplate)
    _LOGGER.debug("Effektvakt-kortet serveres fra %s (v%s)", FRONTEND_URL_BASE, versjon)


def _finn_entry(hass: HomeAssistant, entity_id: str | None) -> ConfigEntry | None:
    """Entryen en forespoersel gjelder: via entiteten, ellers den eneste vi har."""
    if entity_id:
        entitet = er.async_get(hass).async_get(entity_id)
        if entitet is not None and entitet.config_entry_id:
            entry = hass.config_entries.async_get_entry(entitet.config_entry_id)
            if entry is not None and entry.domain == DOMAIN:
                return entry

    entries = hass.config_entries.async_entries(DOMAIN)
    if len(entries) == 1:
        return entries[0]
    return None


def _kapasitetstrinn(entry: ConfigEntry) -> list[tuple[float, int]]:
    """Trinn fra coordinatoren naar entryen er lastet, ellers rett fra config."""
    coordinator = getattr(entry, "runtime_data", None)
    trinn = getattr(coordinator, "kapasitetstrinn", None)
    if trinn:
        return [(float(t[0]), int(t[1])) for t in trinn]

    custom = entry.data.get(CONF_KAPASITETSTRINN_CUSTOM)
    if custom:
        return [(float(t[0]), int(t[1])) for t in custom]
    dso_info = KAPASITETSTRINN_PER_DSO.get(entry.data.get(CONF_DSO, ""))
    return list(dso_info["kapasitetstrinn"]) if dso_info else []


def _dso_navn(entry: ConfigEntry) -> str | None:
    dso_info = KAPASITETSTRINN_PER_DSO.get(entry.data.get(CONF_DSO, ""))
    return dso_info["navn"] if dso_info else None


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_FACEPLATE,
        vol.Optional("entity_id"): str,
        vol.Optional("maks_kw"): vol.All(vol.Coerce(float), vol.Range(min=1, max=200)),
    }
)
@websocket_api.async_response
async def ws_faceplate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Gi kortet skiven som SVG, med skalaen og nettselskapet den er tegnet for."""
    entry = _finn_entry(hass, msg.get("entity_id"))
    if entry is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            "Fant ingen Effektvakt-oppsett for forespoerselen",
        )
        return

    maks_kw = normaliser_maks_kw(float(msg.get("maks_kw", MAKS_KW_STANDARD)))
    dso_navn = _dso_navn(entry)
    svg = generate_faceplate(
        kapasitetstrinn=_kapasitetstrinn(entry),
        maks_kw=maks_kw,
        variant="card",
        dso_navn=dso_navn,
    )
    connection.send_result(msg["id"], {"svg": svg, "maks_kw": maks_kw, "dso_navn": dso_navn})
