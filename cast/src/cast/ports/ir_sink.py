"""Port: where a compiled Cast goes next."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..compiler.typed_ir import Cast


class IRSink(ABC):
    @abstractmethod
    def emit(self, cast: Cast) -> None:
        """Accept a compiled candidate.

        Implementations must NOT verify - that is Assay's job. Conflating the
        two would let a sink promote something unverified.
        """
