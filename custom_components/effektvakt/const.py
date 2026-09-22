"""Constants for Effektvakt integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final[str] = "effektvakt"

# Config keys
CONF_DSO: Final[str] = "dso"
CONF_POWER_SENSOR: Final[str] = "power_sensor"
CONF_ENERGY_SENSOR: Final[str] = "energy_sensor"
CONF_KAPASITETSTRINN_CUSTOM: Final[str] = "kapasitetstrinn_custom"
CONF_SAFETY_BUFFER_KW: Final[str] = "safety_buffer_kw"
CONF_MIN_RISIKO_FOR_KUTT: Final[str] = "min_risiko_for_kutt"
CONF_RISIKO_HOLDETID_MINUTTER: Final[str] = "risiko_holdetid_minutter"
CONF_CONFIRM_PEAK_SENSOR: Final[str] = "confirm_peak_sensor"
CONF_VVB_POWER_SENSOR: Final[str] = "vvb_power_sensor"
CONF_EKSTRA_POWER_SENSORS: Final[str] = "ekstra_power_sensors"
CONF_KUTT_STRATEGI: Final[str] = "kutt_strategi"

# Kutt-strategier
STRATEGI_BLIND: Final[str] = "blind"
STRATEGI_VVB_STATUS: Final[str] = "vvb_status"
STRATEGI_VVB_PLUSS_EKSTRA: Final[str] = "vvb_pluss_ekstra"

STRATEGI_OPTIONS: Final[list[str]] = [STRATEGI_BLIND, STRATEGI_VVB_STATUS, STRATEGI_VVB_PLUSS_EKSTRA]

DEFAULT_KUTT_STRATEGI: Final[str] = STRATEGI_BLIND

# Bakoverkompatibilitet for strategi-navn
LEGACY_STRATEGI_MAPPING: Final[dict[str, str]] = {
    "vvb_billader": STRATEGI_VVB_PLUSS_EKSTRA,
}

# Antagelser per strategi
BLIND_ASSUMED_KUTT_KW: Final[float] = 0.3  # 2 kW VVB x 15% duty cycle
VVB_ACTIVE_THRESHOLD_W: Final[float] = 1000.0  # under denne: element antas å ikke varme
EKSTRA_SENSOR_ACTIVE_THRESHOLD_W: Final[float] = 100.0  # under denne: bidrar ikke

# Risiko-nivåer (sortert: lavest til høyest)
#
# Verdiene sier hvor nær neste kapasitetstrinn projeksjonen ligger, ikke et
# abstrakt risikonivå. En automasjon som sammenligner mot "over_terskel" er
# lesbar uten oppslagstabell, og verdien står seg i loggen og i
# utviklerverktøyene der oversettelsen ikke rendres.
#
# Rekkefølgen i RISIKO_LEVELS er ordningen min_risiko_for_kutt sammenlignes
# etter. Flytter du en verdi, flytter du terskelen for alle som har valgt den.
RISIKO_GOD_MARGIN: Final[str] = "god_margin"
RISIKO_NAERMER_SEG: Final[str] = "naermer_seg_terskel"
RISIKO_LIKE_UNDER: Final[str] = "like_under_terskel"
RISIKO_OVER_TERSKEL: Final[str] = "over_terskel"

RISIKO_LEVELS: Final[list[str]] = [
    RISIKO_GOD_MARGIN,
    RISIKO_NAERMER_SEG,
    RISIKO_LIKE_UNDER,
    RISIKO_OVER_TERSKEL,
]
RISIKO_RANK: Final[dict[str, int]] = {nivå: idx for idx, nivå in enumerate(RISIKO_LEVELS)}

# Bakoverkompatibilitet for risiko-verdier. De gamle verdiene ligger lagret i
# config entryen som min_risiko_for_kutt og i hysterese-tilstanden på disk. Uten
# denne ville et lagret "medium" falt utenfor RISIKO_RANK, og binary-sensoren
# aldri slått på igjen.
LEGACY_RISIKO_MAPPING: Final[dict[str, str]] = {
    "none": RISIKO_GOD_MARGIN,
    "low": RISIKO_NAERMER_SEG,
    "medium": RISIKO_LIKE_UNDER,
    "high": RISIKO_OVER_TERSKEL,
}

# Default values
DEFAULT_DSO: Final[str] = "bkk"
DEFAULT_SAFETY_BUFFER_KW: Final[float] = 1.0
DEFAULT_MIN_RISIKO_FOR_KUTT: Final[str] = RISIKO_LIKE_UNDER
DEFAULT_RISIKO_HOLDETID_MINUTTER: Final[int] = 5

# Tick-intervaller per risiko-nivå (sekunder)
TICK_INTERVAL_BY_RISIKO: Final[dict[str, int]] = {
    RISIKO_GOD_MARGIN: 60,
    RISIKO_NAERMER_SEG: 60,
    RISIKO_LIKE_UNDER: 30,
    RISIKO_OVER_TERSKEL: 15,
}

# Hovedbryter: én switch per config entry som slår all Effektvakt-automatikk av.
# Nøkkelen inngår i unique_id, så den er låst av entitetsregisteret og kan ikke
# endres uten å gi brukeren en ny entitet.
SWITCH_KEY_AUTOMATIKK: Final[str] = "automatikk"
DEFAULT_AUTOMATIKK_AKTIV: Final[bool] = True

# Watchdog
WATCHDOG_INTERVAL_SECONDS: Final[int] = 60
WATCHDOG_STALE_THRESHOLD_SECONDS: Final[int] = 120

# Storage
STORAGE_VERSION: Final[int] = 1

# Frontend: kortet serveres av integrasjonen selv, ingen HACS-plugin.
# Katalogen heter www/ etter HA-konvensjonen, og maa ikke hete frontend/:
# da ville den skygget for modulen frontend.py i samme pakke.
FRONTEND_URL_BASE: Final[str] = "/effektvakt-static"
FRONTEND_DIR_NAME: Final[str] = "www"
FRONTEND_CARD_FILENAME: Final[str] = "effektvakt-card.js"
WS_TYPE_FACEPLATE: Final[str] = "effektvakt/faceplate"

# Peak-sensor-detection mønstre
PEAK_SENSOR_NAME_PATTERNS: Final[list[str]] = [
    "_max_power",
    "_peak_",
    "_peak",
    "_max_per_hour",
    "_average_",
    "_avg_",
]
PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS: Final[list[str]] = ["max", "peak", "average"]

# Validation
VALID_POWER_UNITS: Final[frozenset[str]] = frozenset({"W", "kW"})
VALID_ENERGY_UNITS: Final[frozenset[str]] = frozenset({"Wh", "kWh"})

MAX_POWER_CLAMP_W: Final[int] = 100_000  # 100 kW absolutt øvre grense
MAX_ENERGY_DELTA_KWH: Final[float] = 50.0  # ingen 50+ kWh delta per minutt
