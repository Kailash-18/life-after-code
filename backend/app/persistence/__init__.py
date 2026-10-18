"""
Project Sentinel Persistence Package.
Provides SentinelRepository interface, SQLite persistence adapter, InMemory test double, and factory.
"""

from app.persistence.base import SentinelRepository
from app.persistence.factory import get_repository, reset_repository_instance
from app.persistence.memory import InMemorySentinelRepository
from app.persistence.sqlite import SqliteSentinelRepository

__all__ = [
    "InMemorySentinelRepository",
    "SentinelRepository",
    "SqliteSentinelRepository",
    "get_repository",
    "reset_repository_instance",
]
