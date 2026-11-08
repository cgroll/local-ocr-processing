"""Command: one PDF in, Markdown plus media out (no manifest, no global state).

    uv run python -m docparse.pdf_ingest --pdf FILE --out DIR [--stage extract|render|all]
        [--no-layout] [--ocr auto|off] [--toc FILE]

Contract (used by kh-ingestion, which runs it as a subprocess and only passes paths):

  --stage extract   reads the text layer, detects scanned pages, runs the layout model on all pages
                    and OCR on scanned ones, one model at a time. Writes DIR/toc_candidates.json
                    ({n_pages, bookmarks, pages: [{page, text}], headings: [{level, text, page}]}) and the
                    working files in DIR/_work. No GPU without layout and without scanned pages.
  --stage render    needs a finished extract. Reads --toc FILE if given
                    ({printed_toc: [entry]|null, toc_pages: [pdf page]|null, headings: [entry]|null, model}, entries
                    {number, title, printed_page|pdf_page, level, kind chapter|figure|table}),
                    checks the entries against the page texts and writes DIR/document.md,
                    DIR/media/* (including `cover.jpg`, page 1 at 600 px width, the item's thumbnail) and DIR/run.json.
  --stage all       extract + render without a --toc file (bookmarks, else headings).

  document.md: optional `## Inhaltsverzeichnis` (+ `## Abbildungen`, `## Tabellen`), then one
  `## Seite N[ · gedruckt S. M]` per PDF page; headings below as `###`..`#####`; images and crops as
  `![..](media/<file>)`. run.json: pages, title, author, created, cover, stage (text|layout), layout_error,
  ocr_pages, toc {source, entries, confirmed, model}, printed_pages, versions, seconds.
  stderr: lines `progress <what> <done>/<total>` and `warning: ...`.
  Exit codes: 0 ok, 2 input rejected (not a PDF, encrypted, > 500 pages), 1 other failure.
"""
import argparse
import sys
from pathlib import Path

from . import pipeline as P


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="docparse.pdf_ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stage", choices=("extract", "render", "all"), default="all")
    ap.add_argument("--no-layout", action="store_true", help="text layer only (no layout model)")
    ap.add_argument("--ocr", choices=("auto", "off"), default="auto")
    ap.add_argument("--toc", type=Path, help="table of contents read by a model (stage render)")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    opts = P.Options(layout=not args.no_layout, ocr=args.ocr)
    try:
        if args.stage in ("extract", "all"):
            P.extract(args.pdf, args.out, opts)
        if args.stage in ("render", "all"):
            P.render(args.pdf, args.out, args.toc)
    except P.InputError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return P.EXIT_INPUT
    return 0


if __name__ == "__main__":
    sys.exit(main())
