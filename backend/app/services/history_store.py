"""Bounded in-memory simulation history."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Any, Iterator, List, Optional


class HistoryStore:
    def __init__(self, max_entries: int = 100) -> None:
        self._max = max_entries
        self._data: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = Lock()

    def add(self, simulation_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            if simulation_id in self._data:
                del self._data[simulation_id]
            self._data[simulation_id] = record
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def get(self, simulation_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._data.get(simulation_id)

    def list_recent(self) -> List[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._data.values()))
