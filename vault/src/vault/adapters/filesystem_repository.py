"""Filesystem-backed artifact store — the default Vault.

Local-first by design. An ingot is a file in a directory; nothing here requires
a service, a database, or a network. Swapping to S3 for a team-shared Vault is a
config change, because both implement `ArtifactRepository`.

Lives alongside Crew's own state at `~/.kiro/crew/ingots/`, so a single
directory holds every trace, every artifact, and every proof the system has
accumulated — and a single backup captures all of it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..models.ingot_artifact import Ingot
from ..ports.artifact_repository import ArtifactRepository

DEFAULT_VAULT = Path(
    os.path.expanduser(os.environ.get("QUENCH_VAULT", "~/.kiro/crew/ingots"))
)


class FilesystemRepository(ArtifactRepository):
    """Stores ingots as `<vault>/<ingot_id>.ingot`."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else DEFAULT_VAULT
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ingot_id: str) -> Path:
        # Ingot ids are hex digests, but never trust an id enough to let it
        # traverse: an ingot may have arrived from Exchange.
        safe = "".join(c for c in ingot_id if c.isalnum() or c in "-_")
        if not safe or safe != ingot_id:
            raise ValueError(f"unsafe ingot id: {ingot_id!r}")
        return self.root / f"{safe}.ingot"

    def put(self, ingot: Ingot) -> str:
        path = self._path(ingot.ingot_id)
        # Write-then-rename, so a crash never leaves a half-written artifact
        # that would fail signature verification for the wrong reason.
        tmp = path.with_suffix(".ingot.tmp")
        tmp.write_text(ingot.to_json())
        tmp.replace(path)
        return str(path)

    def get(self, ingot_id: str) -> Ingot | None:
        path = self._path(ingot_id)
        if not path.exists():
            return None
        return Ingot.load(path)

    def list(self) -> list[Ingot]:
        out: list[Ingot] = []
        for path in sorted(self.root.glob("*.ingot")):
            try:
                out.append(Ingot.load(path))
            except (ValueError, json.JSONDecodeError):
                # A malformed artifact must not make the whole Vault unreadable.
                continue
        return out

    def revoke(self, ingot_id: str) -> bool:
        """Mark an ingot revoked. Immediate and one-way.

        The artifact is kept rather than deleted: an audit trail that can be
        made to forget a revoked artifact is not an audit trail. Mill refuses to
        execute anything with this flag set.
        """
        ingot = self.get(ingot_id)
        if ingot is None:
            return False
        path = self._path(ingot_id)
        data = ingot.to_dict()
        data["revoked"] = True
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        return True
