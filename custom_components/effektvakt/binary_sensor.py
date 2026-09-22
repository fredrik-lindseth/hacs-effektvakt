"""Binary sensor for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import ENTITY_ID_FORMAT, BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RISIKO_RANK

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import EffektvaktCoordinator

# Inngår i unique_id, så den er låst av entitetsregisteret.
BINARY_SENSOR_KEY = "kutt_ned_anbefalt"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EffektvaktCoordinator = entry.runtime_data
    async_add_entities([EffektvaktKuttNedAnbefaltBinarySensor(coordinator)])


class EffektvaktKuttNedAnbefaltBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """`on` når hysteresefull risiko >= min_risiko_for_kutt.

    Hovedbryteren rører ikke denne. Sensoren sier «dette burde kuttes», ikke
    «dette blir kuttet»: lar vi den følge bryteren, lyver historikken om hvor
    ofte det faktisk var grunn til å kutte, og et dashboard ville vist alt
    grønt i en time som er på vei over trinnet. Hvorvidt noen gjør noe med
    anbefalingen ligger i attributtet automatikk_aktiv i stedet.
    """

    _attr_has_entity_name = True
    _attr_translation_key = BINARY_SENSOR_KEY

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        super().__init__(coordinator)
        # Samme grunn som i sensor.py: object_id-en utledes ellers av det
        # engelske navnet, og docs og blueprintene navngir den norske id-en.
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{BINARY_SENSOR_KEY}")
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{BINARY_SENSOR_KEY}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Effektvakt",
            manufacturer="Effektvakt",
            model="Kapasitetstrinn-styring",
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        nivå = self.coordinator.data.get("risiko_niva")
        if nivå is None:
            return None
        threshold = self.coordinator.min_risiko_for_kutt
        return RISIKO_RANK.get(nivå, -1) >= RISIKO_RANK.get(threshold, 99)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Bryterens stilling, slik at et dashboard slipper å slå opp
        entitets-id-en til en switch som avhenger av config entryen."""
        return {"automatikk_aktiv": self.coordinator.automatikk_aktiv}
