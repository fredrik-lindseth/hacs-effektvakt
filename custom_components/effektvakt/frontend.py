"""Servering av Effektvakt sitt eget Lovelace-kort.

Integrasjonen tar med seg kortet selv: filene under ``www/`` serveres paa
``/effektvakt-static``, og URL-en meldes inn i Lovelace sitt ressursregister
slik at Fredrik slipper aa gjoere det for haand. Skiven hentes over websocket i
stedet for aa bli tegnet i JavaScript, saa kortet og trykkfilen aldri kan drifte
fra hverandre.

Ressursregisteret er ikke valgt av vane. ``add_extra_js_url`` legger bare et
``import()`` i index-HTML-en som ingen venter paa, mens Lovelace laster og
venter paa ressursene i registeret foer dashbordet tegnes. Uten varm cache rakk
kortet derfor aldri aa definere seg foer viewet ble bygget, og begge kortene kom
opp som «Konfigurasjonsfeil».
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
from .faceplate import (
    MAKS_KW_STANDARD,
    PALETT,
    STILER,
    STILNAVN,
    generate_faceplate,
    normaliser_maks_kw,
    tilgjengelige_stiler,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Engangsarbeidet hoerer til HA-oppstarten, ikke til en config entry. Flagget
# hindrer at det gjoeres to ganger: async_register_static_paths feiler paa en
# URL som alt er tatt, og websocket-kommandoen kan bare registreres en gang.
DATA_FRONTEND_REGISTRERT: str = f"{DOMAIN}_frontend_registrert"

FRONTEND_DIR: Path = Path(__file__).parent / FRONTEND_DIR_NAME

# Lovelace legger LovelaceData paa denne noekkelen. Vi leser den framfor aa
# importere fra homeassistant.components.lovelace: der er alt internt.
LOVELACE_DATA_KEY: str = "lovelace"
RESSURS_TYPE_MODUL: str = "module"

KORT_URL_BASIS: str = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"

# Foerste oppfoering i stilregisteret er standardskiven.
STIL_STANDARD: str = STILNAVN[0]


async def _kort_url(hass: HomeAssistant) -> str:
    """Kort-URL med cache-buster.

    Uten ``?v=`` serverer nettleseren forrige versjon av kortet etter en
    oppdatering av integrasjonen, siden filene serveres med cache-headere.
    """
    integration = await async_get_integration(hass, DOMAIN)
    versjon = str(integration.version) if integration.version else "0"
    return f"{KORT_URL_BASIS}?v={versjon}"


def _lovelace_ressurser(hass: HomeAssistant) -> Any | None:
    """Ressurssamlingen vi kan skrive kort-URL-en inn i, eller None.

    None betyr enten at Lovelace ikke er lastet, eller at ressursene kommer fra
    ``configuration.yaml``. YAML-samlingen er skrivebeskyttet og har ingen
    ``async_create_item``, saa den kjenner vi igjen paa nettopp det.
    """
    lovelace = hass.data.get(LOVELACE_DATA_KEY)
    ressurser = getattr(lovelace, "resources", None)
    if ressurser is None or not hasattr(ressurser, "async_create_item"):
        return None
    return ressurser


def _uten_cache_buster(url: str) -> str:
    return url.split("?", 1)[0]


def _vaare_oppforinger(ressurser: Any) -> list[dict[str, Any]]:
    """Oppfoeringene som peker paa kortet vaart, uansett hvilken ?v= de har."""
    return [i for i in ressurser.async_items() if _uten_cache_buster(i.get("url", "")) == KORT_URL_BASIS]


async def _sett_lovelace_ressurs(hass: HomeAssistant, kort_url: str) -> bool:
    """Sikre noeyaktig en ressursoppfoering for kortet. False: ikke mulig.

    Registeret deles med HACS og med brukeren, saa her skrives det bare naar
    det trengs: finnes oppfoeringen alt med riktig URL, roeres ingenting.
    Endrer versjonen seg, oppdateres den samme oppfoeringen framfor aa faa en
    ny ved siden av, og eventuelle duplikater fra tidligere ryddes bort.
    """
    ressurser = _lovelace_ressurser(hass)
    if ressurser is None:
        return False

    try:
        # Lageret leses lat: uten dette kallet er samlingen tom foerste gang.
        await ressurser.async_get_info()
        vaare = _vaare_oppforinger(ressurser)

        if not vaare:
            await ressurser.async_create_item({"res_type": RESSURS_TYPE_MODUL, "url": kort_url})
            _LOGGER.debug("La Effektvakt-kortet inn som Lovelace-ressurs: %s", kort_url)
            return True

        behold, *duplikater = vaare
        if behold.get("url") != kort_url:
            oppdatering = {"res_type": RESSURS_TYPE_MODUL, "url": kort_url}
            await ressurser.async_update_item(behold["id"], oppdatering)
            _LOGGER.debug("Oppdaterte Lovelace-ressursen for kortet til %s", kort_url)
        for duplikat in duplikater:
            await ressurser.async_delete_item(duplikat["id"])
            _LOGGER.debug("Fjernet duplisert Lovelace-ressurs %s", duplikat.get("url"))
    except Exception:  # et delt register skal aldri kunne velte oppstarten
        _LOGGER.exception("Kunne ikke melde Effektvakt-kortet inn i Lovelace-ressursene")
        return False

    return True


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Server kortet, meld det inn i Lovelace og aapne websocket-kommandoen.

    Trygg aa kalle flere ganger: engangsarbeidet ligger bak et flagg, og
    ressursoppfoeringen skrives bare naar URL-en faktisk har endret seg.
    """
    kort_url = await _kort_url(hass)
    forste_gang = not hass.data.get(DATA_FRONTEND_REGISTRERT)

    if forste_gang:
        hass.data[DATA_FRONTEND_REGISTRERT] = True
        statisk = StaticPathConfig(FRONTEND_URL_BASE, str(FRONTEND_DIR), True)
        await hass.http.async_register_static_paths([statisk])
        websocket_api.async_register_command(hass, ws_faceplate)
        _LOGGER.debug("Effektvakt-kortet serveres fra %s", FRONTEND_URL_BASE)

    if await _sett_lovelace_ressurs(hass, kort_url):
        return

    # Reserveveien, og bare den ene: to veier inn til samme fil gir to
    # innlastinger saa snart URL-ene skiller seg, og da kaster kortets
    # customElements.define paa andre runde. Her kommer vi bare naar Lovelace
    # kjoerer med YAML-ressurser, og da maa brukeren selv legge URL-en inn i
    # configuration.yaml for at kortet skal tegnes ved kald lasting.
    if forste_gang:
        frontend.add_extra_js_url(hass, kort_url)
        _LOGGER.warning(
            "Lovelace-ressursene er i YAML-modus. Legg til url: %s (type: module) "
            "under lovelace.resources i configuration.yaml, ellers kan kortet komme "
            "opp som Konfigurasjonsfeil ved kald lasting",
            kort_url,
        )


async def async_unregister_frontend(hass: HomeAssistant) -> None:
    """Ta kort-URL-en ut av Lovelace-ressursene igjen ved avinstallasjon."""
    ressurser = _lovelace_ressurser(hass)
    if ressurser is None:
        return

    try:
        await ressurser.async_get_info()
        for item in _vaare_oppforinger(ressurser):
            await ressurser.async_delete_item(item["id"])
            _LOGGER.debug("Fjernet Lovelace-ressursen %s", item.get("url"))
    except Exception:  # avinstallasjonen skal fullfoere uansett
        _LOGGER.exception("Kunne ikke fjerne Effektvakt-kortet fra Lovelace-ressursene")


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


def _palett(stil: str) -> dict[str, str]:
    """Fargerollene skiven er tegnet med, slik kortet kan speile dem i CSS.

    Kortet har de samme rollenavnene som reserve, men henter dem herfra saa
    en fargeendring i faceplate.py ikke kan bli staaende igjen i kortet.
    """
    return {**PALETT, **STILER[stil].palett}


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_FACEPLATE,
        vol.Optional("entity_id"): str,
        vol.Optional("maks_kw"): vol.All(vol.Coerce(float), vol.Range(min=1, max=200)),
        vol.Optional("stil"): vol.In(STILNAVN),
    }
)
@websocket_api.async_response
async def ws_faceplate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Gi kortet skiven som SVG, med skala, nettselskap, stilregister og palett."""
    entry = _finn_entry(hass, msg.get("entity_id"))
    if entry is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            "Fant ingen Effektvakt-oppsett for forespoerselen",
        )
        return

    maks_kw = normaliser_maks_kw(float(msg.get("maks_kw", MAKS_KW_STANDARD)))
    stil = str(msg.get("stil", STIL_STANDARD))
    dso_navn = _dso_navn(entry)
    svg = generate_faceplate(
        kapasitetstrinn=_kapasitetstrinn(entry),
        maks_kw=maks_kw,
        variant="card",
        dso_navn=dso_navn,
        stil=stil,
    )
    connection.send_result(
        msg["id"],
        {
            "svg": svg,
            "maks_kw": maks_kw,
            "dso_navn": dso_navn,
            "stil": stil,
            # Kortets stilvelger skal vise registeret, ikke en kopi av det.
            "stiler": tilgjengelige_stiler(),
            "palett": _palett(stil),
        },
    )
