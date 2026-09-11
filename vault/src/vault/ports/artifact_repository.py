"""Port: where sealed artifacts live.

Repository pattern - Vault never assumes a filesystem. Swapping local storage
for a team-shared bucket is a config change, not a code change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ArtifactRepository(ABC):
    @abstractmethod
    def put(self, ingot) -> str: ...

    @abstractmethod
    def get(self, ingot_id: str): ...

    @abstractmethod
    def list(self) -> list: ...

    @abstractmethod
    def revoke(self, ingot_id: str) -> None:
        """Revocation is immediate and irreversible. Sealing is a cache."""
