"""Simulated fault recovery via corrected scenario re-evaluation."""

from __future__ import annotations

from typing import Any, List

from app.models.domain_types import RecoveryStatus
from app.models.simulation import EventSeverity, EventType, SimulationStatus
from app.services.simulation_service import SimulationService


def _active_faults_from_events(events: List[dict]) -> List[dict]:
    active: List[dict] = []
    for e in events:
        if e["severity"] in (EventSeverity.WARNING.value, EventSeverity.CRITICAL.value):
            active.append(
                {
                    "event_type": e["event_type"],
                    "severity": e["severity"],
                    "triggering_value": e["triggering_value"],
                    "threshold": e.get("threshold"),
                    "unit": e["unit"],
                }
            )
    return active


def _is_critical_fault(events: List[dict]) -> bool:
    for e in events:
        if e["severity"] == EventSeverity.CRITICAL.value:
            return True
        if e["event_type"] == EventType.BATTERY_DEPLETION.value:
            return True
    return False


def _build_recovery_actions(before: List[dict], after: List[dict]) -> List[dict]:
    actions: List[dict] = []
    before_types = {f["event_type"] for f in before}
    after_types = {f["event_type"] for f in after}

    guidance = {
        EventType.BATTERY_TEMPERATURE.value: (
            "Reduce battery_temperature_c below the warning/critical demonstration thresholds."
        ),
        EventType.OBSTACLE_PROXIMITY.value: (
            "Increase obstacle_distance_m above the proximity threshold, or set distance to null to omit the warning."
        ),
        EventType.LOW_BATTERY.value: (
            "Increase initial_soc_percent or reduce energy demand (speed, duration, gradient)."
        ),
        EventType.BATTERY_DEPLETION.value: (
            "Increase initial_soc_percent or reduce speed, duration, or uphill gradient so demand fits available energy."
        ),
    }

    for event_type in before_types:
        satisfied = event_type not in after_types
        actions.append(
            {
                "condition": f"Clear simulated {event_type}",
                "satisfied": satisfied,
                "required_input_guidance": guidance.get(event_type, "Adjust inputs that caused this simulated event."),
            }
        )

    for event_type in after_types - before_types:
        actions.append(
            {
                "condition": f"New simulated {event_type} introduced",
                "satisfied": False,
                "required_input_guidance": "Review corrected scenario inputs; new warnings or faults appeared.",
            }
        )

    return actions


class RecoveryService:
    def __init__(self, simulation_service: SimulationService) -> None:
        self.simulation_service = simulation_service

    def recover(self, prior_simulation_id: str, corrected_scenario: dict[str, Any]) -> dict[str, Any]:
        prior = self.simulation_service.history.get(prior_simulation_id)
        if prior is None:
            return {"error": "not_found"}

        before_events = prior["events"]
        before_faults = _active_faults_from_events(before_events)
        prior_status = prior["status"]

        if prior_status not in (
            SimulationStatus.FAULT.value,
            SimulationStatus.WARNING.value,
        ):
            return {
                "error": "invalid_prior_state",
                "detail": "Recovery requires a prior simulation in FAULT or WARNING status.",
                "prior_status": prior_status,
            }

        corrected = self.simulation_service.run_simulation(corrected_scenario, store=True)
        after_events = corrected["events"]
        after_faults = _active_faults_from_events(after_events)

        still_critical = _is_critical_fault(after_events)

        if still_critical:
            recovery_status = RecoveryStatus.STILL_FAULT
        elif not after_faults:
            recovery_status = RecoveryStatus.RECOVERED
        elif _is_critical_fault(before_events) and not still_critical:
            recovery_status = RecoveryStatus.IMPROVED_TO_WARNING
        else:
            recovery_status = RecoveryStatus.STILL_FAULT

        recovery_in_progress = recovery_status in (
            RecoveryStatus.STILL_FAULT,
            RecoveryStatus.IMPROVED_TO_WARNING,
        )

        return {
            "prior_simulation_id": prior_simulation_id,
            "prior_status": prior_status,
            "recovery_status": recovery_status.value,
            "recovery_in_progress": recovery_in_progress,
            "corrected_simulation": corrected,
            "active_faults_before": before_faults,
            "active_faults_after": after_faults,
            "recovery_actions": _build_recovery_actions(before_faults, after_faults),
            "message": (
                "Simulated recovery reflects corrected inputs only; this does not control a physical vehicle. "
                "Status improves only when triggering rules no longer fire."
            ),
        }
