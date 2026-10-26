"""Agent harness entrypoint, runs INSIDE the sandbox container (task 4.1/4.2) -- the container
boundary itself is the isolation (design.md Decision 3), not just `cwd`.

Drives one `ClaudeSDKClient` turn for one question, with the toolset shrunk to `Bash`+`Read`
(design.md Decision 8: the SDK default also includes WebSearch/WebFetch, which would let the
agent bypass the sandboxed corpus entirely -- and a smaller toolset also cuts the per-call
token/cost overhead from tool-definition caching, measured at ~12k tokens / ~$0.10 for the
full default set in task 1.1's smoke test).

Usage (inside the container):
    python sandbox_tools/run_agent.py "What is the PSRR...?" --out /output/result.json
"""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

PROMPT_TEMPLATE = """\
You are investigating a technical-document corpus mounted read-only at /sandbox. Your task:
answer the question below using ONLY content you find under /sandbox. You do not know in
advance which document or page contains the answer -- you must find it yourself.

Question: {question}

Ways to search (use whichever you like, combine as needed):
- `python /app/sandbox_tools/search.py vector "<query>" --top-k <n>` -- semantic vector search
- `python /app/sandbox_tools/search.py fulltext "<query>" --top-k <n>` -- exact keyword search
- Direct exploration of /sandbox/enrich, /sandbox/digest, /sandbox/pages (grep, find, cat, ...)
- Reading any file directly

/sandbox/pages/<doc_id>/<page>.png holds the rendered page image for every page.

IMPORTANT: once you believe you have found the page that answers the question, you MUST open
and actually look at that page's image (/sandbox/pages/<doc_id>/<page>.png) before giving your
final answer -- do not rely solely on extracted/OCR text, which is known to sometimes be wrong
(garbled units, merged table rows). Confirm the answer directly from the image.

End your reply with exactly one line in the form:
ANSWER: <your answer, as short and precise as possible>
"""


def _json_default(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return str(obj)


async def run(question: str, cwd: str) -> dict:
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        tools=["Bash", "Read"],
        cwd=cwd,
        # Default (1 MB) is too small once the agent Reads a large scanned page image -- found
        # on gd1-001028 p1 (3.1 MB PNG, ~4.2 MB base64) during the full run: the SDK's transport
        # raised CLIJSONDecodeError("JSON message exceeded maximum buffer size of 1048576
        # bytes..."). Several other scans in the dataset are in the same size range.
        max_buffer_size=32_000_000,
    )
    messages = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(PROMPT_TEMPLATE.format(question=question))
        async for message in client.receive_response():
            messages.append(message)

    tool_calls = []
    final_text = None
    result: ResultMessage | None = None
    for m in messages:
        if isinstance(m, AssistantMessage):
            for block in m.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls.append({"name": block.name, "input": block.input})
                elif isinstance(block, TextBlock):
                    final_text = block.text  # last AssistantMessage's text wins
        elif isinstance(m, ResultMessage):
            result = m

    return {
        "question": question,
        "final_text": final_text,
        "tool_calls": tool_calls,
        "num_turns": result.num_turns if result else None,
        "duration_ms": result.duration_ms if result else None,
        "duration_api_ms": result.duration_api_ms if result else None,
        "total_cost_usd": result.total_cost_usd if result else None,
        "usage": result.usage if result else None,
        "is_error": result.is_error if result else True,
        "raw_messages": messages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--cwd", default="/sandbox")
    parser.add_argument("--out", default=None, help="write full JSON result here (also printed to stdout)")
    args = parser.parse_args(argv)

    result = anyio.run(run, args.question, args.cwd)
    text = json.dumps(result, indent=1, ensure_ascii=False, default=_json_default)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
