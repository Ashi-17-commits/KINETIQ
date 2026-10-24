"""Battery state-of-charge and energy draw logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.simulation import BatteryState

_EPS = 1e-9


@dataclass(frozen=True)
class BatteryInputs:
    initial_soc_percent: float
    usable_battery_capacity_kwh: float
    # Net battery energy over the trip [kWh]; negative means net regeneration.
    requested_energy_kwh: float
    # Optional per-step net energy [kWh]. When given, SOC is integrated step by step so
    # mid-trip depletion and a full battery refusing regen are handled. Must sum to
    # requested_energy_kwh. When omitted, the trip is treated as a single step.
    energy_steps_kwh: Optional[tuple[float, ...]] = None
    step_durations_s: Optional[tuple[float, ...]] = None


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
    remaining_energy_kwh: float = 0.0
    regen_energy_not_stored_kwh: float = 0.0
    depletion_elapsed_minutes: Optional[float] = None


def compute_battery_state(inputs: BatteryInputs) -> BatteryOutputs:
    capacity = inputs.usable_battery_capacity_kwh
    initial_soc = max(0.0, min(100.0, inputs.initial_soc_percent))
    available = capacity * initial_soc / 100.0
    requested = inputs.requested_energy_kwh
    steps = inputs.energy_steps_kwh if inputs.energy_steps_kwh else (requested,)
    durations = inputs.step_durations_s

    energy = available
    not_stored = 0.0
    depleted = False
    depletion_s: Optional[float] = None
    elapsed_s = 0.0
    for i, step in enumerate(steps):
        next_energy = energy - step
        if next_energy < -_EPS:
            # Battery empties during this step; the vehicle cannot continue.
            depleted = True
            if durations is not None and step > 0:
                depletion_s = elapsed_s + durations[i] * (energy / step)
            energy = 0.0
            break
        if next_energy > capacity:
            not_stored += next_energy - capacity
            next_energy = capacity
        energy = max(0.0, next_energy)
        if durations is not None:
            elapsed_s += durations[i]

    final_soc = max(0.0, min(100.0, energy / capacity * 100.0))
    # Net energy actually taken out of the battery (negative if regen left it fuller).
    energy_drawn = available - energy

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
        trip_completed_in_model=not depleted,
        remaining_energy_kwh=energy,
        regen_energy_not_stored_kwh=not_stored,
        depletion_elapsed_minutes=depletion_s / 60.0 if depletion_s is not None else None,
    )
