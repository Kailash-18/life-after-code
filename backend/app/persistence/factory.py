"""
Factory for instantiating the active SentinelRepository singleton.
"""

from app.config import settings
from app.persistence.base import SentinelRepository
from app.persistence.memory import InMemorySentinelRepository
from app.persistence.sqlite import SqliteSentinelRepository

_REPOSITORY_INSTANCE: SentinelRepository | None = None


def get_repository() -> SentinelRepository:
    """Get or initialize the global SentinelRepository instance."""
    global _REPOSITORY_INSTANCE
    if _REPOSITORY_INSTANCE is None:
        backend = settings.persistence_backend.lower()
        if backend == "memory":
            _REPOSITORY_INSTANCE = InMemorySentinelRepository()
        elif backend == "sqlite":
            _REPOSITORY_INSTANCE = SqliteSentinelRepository(db_path=settings.sqlite_db_path)
        else:
            # Fallback to SQLite
            _REPOSITORY_INSTANCE = SqliteSentinelRepository(db_path=settings.sqlite_db_path)
    return _REPOSITORY_INSTANCE


def reset_repository_instance(new_repo: SentinelRepository | None = None) -> None:
    """Helper to inject or reset repository instance during tests."""
    global _REPOSITORY_INSTANCE
    _REPOSITORY_INSTANCE = new_repo
