"""Hovedbryteren for Effektvakt-automatikken."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_AUTOMATIKK_AKTIV, DOMAIN, SWITCH_KEY_AUTOMATIKK

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import EffektvaktCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sett opp hovedbryteren for denne config entryen."""
    coordinator: EffektvaktCoordinator = entry.runtime_data
    async_add_entities([EffektvaktAutomatikkSwitch(coordinator)])


class EffektvaktAutomatikkSwitch(SwitchEntity, RestoreEntity):
    """Ett sted å slå av all lastkutting.

    Bryteren gjør ingenting med beregningen. Den er et flagg blueprintene
    leser før de kutter, slik at man slipper å huske hvilke automasjoner som
    finnes den dagen man vil ha varmt vann uansett hva det koster. Sensorene,
    og dermed historikken, går videre som før.
    """

    _attr_has_entity_name = True
    _attr_translation_key = SWITCH_KEY_AUTOMATIKK
    _attr_icon = "mdi:shield-home"

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        # Ikke en CoordinatorEntity: tilstanden kommer fra brukeren, ikke fra
        # pollen, så det er ingenting å abonnere på.
        self.coordinator = coordinator
        self._attr_is_on = DEFAULT_AUTOMATIKK_AKTIV
        # Samme grunn som i sensor.py: uten dette utleder HA object_id-en fra
        # det engelske navnet, og bryteren hadde hett
        # switch.effektvakt_automatic_load_cutting i docs og blueprints.
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{SWITCH_KEY_AUTOMATIKK}")
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{SWITCH_KEY_AUTOMATIKK}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Effektvakt",
            manufacturer="Effektvakt",
            model="Kapasitetstrinn-styring",
        )

    async def async_added_to_hass(self) -> None:
        """Hent tilbake tilstanden fra før omstart.

        Alt annet enn et lagret `off` gir på: første oppstart, tapt historikk
        og `unavailable` skal lande på vakt, ikke på fri flyt. Glemmer vi
        hvorfor vakten var av, er det billigere å vekke den enn å la den sove.
        """
        await super().async_added_to_hass()
        forrige = await self.async_get_last_state()
        self._sett_aktiv(not (forrige is not None and forrige.state == STATE_OFF), skriv_state=False)

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Slå automatikken på igjen."""
        self._sett_aktiv(True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Slå automatikken av. Laster som alt er kuttet, kommer tilbake av
        failsafe-timeren i blueprintet, ikke av dette kallet."""
        self._sett_aktiv(False)

    def _sett_aktiv(self, aktiv: bool, *, skriv_state: bool = True) -> None:
        self._attr_is_on = aktiv
        # Coordinatoren holder flagget så binary_sensor-en kan vise det uten
        # å måtte slå opp entitets-id-en vår.
        self.coordinator.automatikk_aktiv = aktiv
        if not skriv_state:
            return
        self.async_write_ha_state()
        # Uten dette skriver binary_sensor-en først attributtet ved neste tikk,
        # og et dashboard ville vist feil stilling i opptil et minutt etter at
        # noen vippet bryteren. Målt til 60 sekunder på ekte oppsett.
        self.coordinator.async_update_listeners()
