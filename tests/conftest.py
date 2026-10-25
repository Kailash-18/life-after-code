"""Root test settings: tests that import the backend use an in-memory store, so no sentinel.db is left behind
and one run's incidents cannot leak into the next."""
import os

os.environ.setdefault("SENTINEL_PERSISTENCE_BACKEND", "memory")
