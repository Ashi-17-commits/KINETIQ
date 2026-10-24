"""Shared domain literals for API validation."""

from __future__ import annotations

from enum import Enum
from typing import Literal

RoadSurface = Literal["dry", "wet", "slippery"]
ObstacleSource = Literal["user_input", "simulated_scenario"]
TrafficProfile = Literal["steady", "free_flow", "moderate_congestion", "stop_and_go"]


class RoadSurfaceEnum(str, Enum):
    DRY = "dry"
    WET = "wet"
    SLIPPERY = "slippery"


class ObstacleSourceEnum(str, Enum):
    USER_INPUT = "user_input"
    SIMULATED_SCENARIO = "simulated_scenario"


class RecoveryStatus(str, Enum):
    STILL_FAULT = "STILL_FAULT"
    IMPROVED_TO_WARNING = "IMPROVED_TO_WARNING"
    RECOVERED = "RECOVERED"
