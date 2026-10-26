"""Task 4.3: turns one `run_agent.py` result JSON into a compact efficiency/outcome summary.
Runs on the HOST, after a container run has written its result (e.g. to /tmp/agent_output/...).

Doc-visit detection is a path-regex heuristic over the tool calls' own arguments (Bash command
text, Read file_path) -- not a precise trace. Documented as an approximation in design.md
("Dokument-Zählung aus Tool-Aufrufen ist nur eine Heuristik"), sufficient for a comparison spike.
"""
import argparse
import json
import re
import sys
from pathlib import Path

_DOC_ID_RE = re.compile(r"/sandbox/(?:pages|digest|enrich)/([^/\s\"']+?)(?:\.md|\.summary\.json|\.cloud_summary\.json)?(?:/|$)")
_ANSWER_RE = re.compile(r"ANSWER:\s*(.+)", re.IGNORECASE)
_SEARCH_MODE_RE = re.compile(r"search\.py\s+(vector|fulltext)")


def _doc_ids_in(text: str) -> set[str]:
    return {m.group(1) for m in _DOC_ID_RE.finditer(text) if m.group(1) not in ("", "DOCUMENT")}


def summarize(result: dict, variant: str, question_id: str | None = None) -> dict:
    tool_calls = result.get("tool_calls", [])
    by_tool: dict[str, int] = {}
    by_search_mode: dict[str, int] = {}
    visited_docs: set[str] = set()
    image_verified = False

    for tc in tool_calls:
        name = tc["name"]
        by_tool[name] = by_tool.get(name, 0) + 1
        arg_text = json.dumps(tc.get("input", {}))
        visited_docs |= _doc_ids_in(arg_text)
        if name == "Bash":
            m = _SEARCH_MODE_RE.search(arg_text)
            if m:
                by_search_mode[m.group(1)] = by_search_mode.get(m.group(1), 0) + 1
        elif name == "Read" and "/sandbox/pages/" in arg_text and ".png" in arg_text:
            image_verified = True

    final_text = result.get("final_text") or ""
    answer_match = _ANSWER_RE.search(final_text)
    usage = result.get("usage") or {}

    return {
        "question_id": question_id,
        "variant": variant,
        "question": result.get("question"),
        "final_answer": answer_match.group(1).strip() if answer_match else final_text.strip(),
        "image_verified": image_verified,
        "tool_calls_total": len(tool_calls),
        "tool_calls_by_tool": by_tool,
        "search_calls_by_mode": by_search_mode,
        "visited_documents": sorted(visited_docs),
        "num_documents_visited": len(visited_docs),
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "total_cost_usd": result.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "is_error": result.get("is_error"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_path", type=Path)
    parser.add_argument("--variant", required=True, choices=["local", "cloud"])
    parser.add_argument("--question-id", default=None)
    args = parser.parse_args(argv)

    result = json.loads(args.result_path.read_text(encoding="utf-8"))
    print(json.dumps(summarize(result, args.variant, args.question_id), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
