"""In-Memory-Cache (User-Direktive 24.06.2026).

Einfacher TTL-Cache fuer haeufig abgefragte Daten (z.B. Project-Listen).
Vermeidet wiederholte DB-Queries bei identischen Anfragen.

Thread-safe via threading.Lock.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple


class SimpleCache:
    """Sehr einfacher In-Memory TTL-Cache mit Mutex-Locking."""

    def __init__(self):
        self._data: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Holt Wert aus Cache. Gibt None zurueck wenn nicht da oder abgelaufen."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.time() > expires_at:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float = 5.0) -> None:
        """Setzt Wert mit TTL (Sekunden)."""
        with self._lock:
            self._data[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        """Loescht einzelnen Eintrag."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Loescht alle Eintraege."""
        with self._lock:
            self._data.clear()


# Globaler Cache (Singleton)
_cache: Optional[SimpleCache] = None


def get_cache() -> SimpleCache:
    """Lazy-Init fuer globalen Cache (Process-übergreifend im selben Worker)."""
    global _cache
    if _cache is None:
        _cache = SimpleCache()
    return _cache


def invalidate_cache(key: Optional[str] = None) -> None:
    """Invalidiert einen Key oder alle Keys."""
    cache = get_cache()
    if key:
        cache.delete(key)
    else:
        cache.clear()
