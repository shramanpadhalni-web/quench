"""Expose Quench as MCP tools, so any MCP-speaking agent can drive it.

This is the portability play: an agent does not need to be written in Python,
or know what Kiro is, to observe its own workflows and seal them.
"""

from __future__ import annotations

from .wiring import build


def serve_mcp() -> int:
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("quench")

    @mcp.tool()
    def quench_candidates() -> list[dict]:
        """List workflows discovered from observed traces, with lifecycle state."""
        return build().candidates()

    @mcp.tool()
    def quench_state() -> dict:
        """Lifecycle state of every observed workflow."""
        return build().state()

    @mcp.tool()
    def quench_seal(index: int) -> dict:
        """Verify a candidate and, if it passes, sign it and enter Shadow Mode.

        Does not authorise execution: a signed artifact must still earn its way
        to Sealed through shadow comparison.
        """
        return build().seal(index)

    @mcp.tool()
    def quench_inspect(ingot_id: str) -> dict:
        """What a sealed artifact will do, and what it was proven against."""
        app = build()
        ingot = app.vault.get(ingot_id)
        if ingot is None:
            raise ValueError(f"no ingot {ingot_id}")
        return {
            "ingot_id": ingot.ingot_id,
            "revoked": ingot.revoked,
            "provenance": ingot.hallmark.get("provenance", {}),
            "steps": [s.to_dict() for s in ingot.steps],
        }

    @mcp.tool()
    def quench_revoke(skill_id: str) -> dict:
        """Revoke a workflow. Immediate and terminal."""
        return build().revoke(skill_id)

    mcp.run()
    return 0
