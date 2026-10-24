"""Battery state-of-charge and energy draw logic."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.simulation import BatteryState


@dataclass(frozen=True)
class BatteryInputs:
    initial_soc_percent: float
    usable_battery_capacity_kwh: float
    requested_energy_kwh: float


@dataclass(frozen=True)
class BatteryOutputs:
    initial_soc_percent: float
    final_soc_percent: float
    usable_battery_capacity_kwh: float
    available_energy_kwh: float
    requested_energy_kwh: float
    energy_drawn_kwh: float
    energy_supplied_kwh: float
    battery_depleted: bool
    battery_state: BatteryState
    depletion_note: str | None
    trip_completed_in_model: bool


def compute_battery_state(inputs: BatteryInputs) -> BatteryOutputs:
    capacity = inputs.usable_battery_capacity_kwh
    initial_soc = max(0.0, min(100.0, inputs.initial_soc_percent))
    available = capacity * initial_soc / 100.0
    requested = max(0.0, inputs.requested_energy_kwh)

    energy_drawn = min(requested, available)
    final_soc = initial_soc - (energy_drawn / capacity * 100.0)
    final_soc = max(0.0, min(100.0, final_soc))

    depleted = requested > available + 1e-12
    note: str | None = None
    if depleted:
        note = (
            "Requested energy exceeds available battery energy for this interval; "
            "the simplified model cannot supply the full duration at the computed demand."
        )

    if depleted:
        state = BatteryState.DEPLETED
    elif final_soc <= 0.0 and initial_soc <= 0.0:
        state = BatteryState.DEPLETED
    else:
        state = BatteryState.NORMAL

    trip_completed = not depleted

    return BatteryOutputs(
        initial_soc_percent=initial_soc,
        final_soc_percent=final_soc,
        usable_battery_capacity_kwh=capacity,
        available_energy_kwh=available,
        requested_energy_kwh=requested,
        energy_drawn_kwh=energy_drawn,
        energy_supplied_kwh=energy_drawn,
        battery_depleted=depleted,
        battery_state=state,
        depletion_note=note,
        trip_completed_in_model=trip_completed,
    )
