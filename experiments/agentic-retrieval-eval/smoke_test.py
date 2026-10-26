"""Task 1.1: smallest possible check that the Claude Agent SDK can authenticate and run from
inside a container, using only a redacted CLAUDE_CONFIG_DIR (claudeAiOauth token only, see
Dockerfile.smoke) -- no ANTHROPIC_API_KEY, no mount of the host's full ~/.claude/.

Not part of the actual eval harness; throwaway script for the risk check in tasks.md 1.1.
"""
import anyio

from claude_agent_sdk import ClaudeAgentOptions, query


async def main() -> None:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    async for message in query(prompt="Reply with exactly: OK", options=options):
        print(f"[{type(message).__name__}] {message}")


if __name__ == "__main__":
    anyio.run(main)
