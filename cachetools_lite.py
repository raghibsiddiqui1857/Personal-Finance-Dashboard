"""Minimal thread-safe TTL cache (swap for Redis when running multiple workers)."""
import threading
import time


class TTLCache:
    def __init__(self, ttl=30):
        self.ttl, self._d, self._lock = ttl, {}, threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._d.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1]
            self._d.pop(key, None)

    def set(self, key, value):
        with self._lock:
            self._d[key] = (time.time(), value)

    def clear(self):
        with self._lock:
            self._d.clear()
