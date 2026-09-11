"""Hallmark — Ed25519 signing and the provenance record.

The Hallmark is what makes an `.ingot` trustworthy when it travels. Without it a
compiled workflow is a file someone could have edited; with it, a consumer can
establish what verified this artifact, against how many traces, under which
strategy, and when.

**This is the part no other system in the field has.** Malik's crystallised
playbooks are internal Azure infrastructure; LOOP's templates live inside the
LOOP engine. Neither produces a transferable, independently verifiable object.
See `docs/COMPETITIVE-LANDSCAPE.md` §5.1.

The signing key lives outside the artifact store — deliberately mirroring how
Crew keeps its SEL HMAC key in `trust/` rather than beside the log it signs.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

DEFAULT_KEY_DIR = Path(
    os.path.expanduser(os.environ.get("QUENCH_TRUST_DIR", "~/.kiro/crew/trust"))
)
KEY_NAME = "quench_signing.key"


@dataclass(frozen=True)
class Provenance:
    """What a consumer needs in order to decide whether to trust an artifact."""

    cast_id: str
    skill_signature: str
    trace_count: int
    #: Every verification strategy that passed, by name.
    verified_by: tuple[str, ...]
    #: Where the traces came from, for auditing.
    trace_source: str
    sealed_at: str
    quench_version: str = "0.1.0"

    def canonical(self) -> bytes:
        """Deterministic bytes to sign. Key order and separators are fixed."""
        payload = asdict(self)
        payload["verified_by"] = list(payload["verified_by"])
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class Hallmark:
    """A signature plus the provenance it attests to."""

    provenance: Provenance
    signature_hex: str
    public_key_hex: str
    algorithm: str = "ed25519"

    def to_dict(self) -> dict:
        payload = asdict(self.provenance)
        payload["verified_by"] = list(payload["verified_by"])
        return {
            "provenance": payload,
            "signature": self.signature_hex,
            "public_key": self.public_key_hex,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Hallmark":
        provenance = dict(data["provenance"])
        provenance["verified_by"] = tuple(provenance.get("verified_by", ()))
        return cls(
            provenance=Provenance(**provenance),
            signature_hex=data["signature"],
            public_key_hex=data["public_key"],
            algorithm=data.get("algorithm", "ed25519"),
        )


class Signer:
    """Signs verified Casts. One key per installation."""

    def __init__(self, key_dir: Path | None = None) -> None:
        self.key_dir = Path(key_dir) if key_dir else DEFAULT_KEY_DIR
        self.key_path = self.key_dir / KEY_NAME

    def _load_or_create(self) -> Ed25519PrivateKey:
        if self.key_path.exists():
            return serialization.load_pem_private_key(
                self.key_path.read_bytes(), password=None
            )
        self.key_dir.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        self.key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        # Owner-only. A world-readable signing key is not a signing key.
        self.key_path.chmod(0o600)
        return key

    def sign(self, cast, verified_by: tuple[str, ...], trace_source: str) -> Hallmark:
        """Sign a **verified** Cast.

        The caller is responsible for having run verification. This class does
        not check — signing an unverified Cast is possible, and preventing that
        is precisely the Kernel state machine's job, not the signer's.
        """
        key = self._load_or_create()

        provenance = Provenance(
            cast_id=cast.cast_id,
            skill_signature=cast.skill_signature,
            trace_count=cast.trace_count,
            verified_by=tuple(verified_by),
            trace_source=trace_source,
            sealed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        signature = key.sign(provenance.canonical())

        return Hallmark(
            provenance=provenance,
            signature_hex=signature.hex(),
            public_key_hex=key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            .hex(),
        )


def verify(hallmark: Hallmark) -> bool:
    """Check a Hallmark's signature against its own provenance.

    Note carefully what this does and does not establish. It proves the
    provenance record has not been altered since signing. It does **not** prove
    the signer is trustworthy — that is the consumer's decision, made by
    comparing ``public_key`` against keys they have chosen to trust.
    """
    try:
        public = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(hallmark.public_key_hex)
        )
        public.verify(
            bytes.fromhex(hallmark.signature_hex), hallmark.provenance.canonical()
        )
        return True
    except (InvalidSignature, ValueError):
        return False
