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
CONF_BILLADER_POWER_SENSOR: Final[str] = "billader_power_sensor"
CONF_KUTT_STRATEGI: Final[str] = "kutt_strategi"

# Kutt-strategier
STRATEGI_BLIND: Final[str] = "blind"
STRATEGI_VVB_STATUS: Final[str] = "vvb_status"
STRATEGI_VVB_BILLADER: Final[str] = "vvb_billader"

STRATEGI_OPTIONS: Final[list[str]] = [STRATEGI_BLIND, STRATEGI_VVB_STATUS, STRATEGI_VVB_BILLADER]

DEFAULT_KUTT_STRATEGI: Final[str] = STRATEGI_BLIND

# Antagelser per strategi
BLIND_ASSUMED_KUTT_KW: Final[float] = 0.3  # 2 kW VVB x 15% duty cycle
VVB_ACTIVE_THRESHOLD_W: Final[float] = 1000.0  # under denne: element antas å ikke varme

# Default values
DEFAULT_DSO: Final[str] = "bkk"
DEFAULT_SAFETY_BUFFER_KW: Final[float] = 1.0
DEFAULT_MIN_RISIKO_FOR_KUTT: Final[str] = "medium"
DEFAULT_RISIKO_HOLDETID_MINUTTER: Final[int] = 5

# Risiko-nivåer (sortert: lavest til høyest)
RISIKO_NONE: Final[str] = "none"
RISIKO_LOW: Final[str] = "low"
RISIKO_MEDIUM: Final[str] = "medium"
RISIKO_HIGH: Final[str] = "high"

RISIKO_LEVELS: Final[list[str]] = [RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH]
RISIKO_RANK: Final[dict[str, int]] = {nivå: idx for idx, nivå in enumerate(RISIKO_LEVELS)}

# Tick-intervaller per risiko-nivå (sekunder)
TICK_INTERVAL_BY_RISIKO: Final[dict[str, int]] = {
    RISIKO_NONE: 60,
    RISIKO_LOW: 60,
    RISIKO_MEDIUM: 30,
    RISIKO_HIGH: 15,
}

# Watchdog
WATCHDOG_INTERVAL_SECONDS: Final[int] = 60
WATCHDOG_STALE_THRESHOLD_SECONDS: Final[int] = 120

# Storage
STORAGE_VERSION: Final[int] = 1

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
