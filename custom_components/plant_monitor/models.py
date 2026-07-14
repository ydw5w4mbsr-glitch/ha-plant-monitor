"""Data models for the Plant Monitor integration."""

from dataclasses import dataclass
from enum import StrEnum


class PlantStatus(StrEnum):
    """Possible status values for a monitored plant."""

    OK = "ok"
    DRY = "dry"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class PlantConfig:
    """Immutable configuration for one plant."""

    subentry_id: str
    name: str
    moisture_sensor: str
    dry_below: float
    clear_at: float


@dataclass(slots=True)
class PlantState:
    """Current runtime state for one plant."""

    config: PlantConfig
    status: PlantStatus = PlantStatus.UNAVAILABLE
    watering_needed: bool = False
    moisture: float | None = None
