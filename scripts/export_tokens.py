#!/usr/bin/env python3
"""Copy the design tokens out of assets/coach.html into design/tokens.css.

The page is one self-contained file, so the tokens live in it, between the markers
`/* tokens:start` and `/* tokens:end */`. This script publishes that block as a stand-alone stylesheet that
other projects can link. Run it after changing a colour, radius or font in the page:

    python3 scripts/export_tokens.py          # write design/tokens.css
    python3 scripts/export_tokens.py --check  # fail if design/tokens.css is out of date
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE, OUT = ROOT / "assets" / "coach.html", ROOT / "design" / "tokens.css"
HEAD = """/*
 * Recording Assistant design tokens: day (:root) and night ([data-theme="dark"], and prefers-color-scheme: dark
 * unless [data-theme="light"] is set). Generated from assets/coach.html by scripts/export_tokens.py; do not
 * edit by hand. What the tokens mean and how to use them: design/DESIGN.md.
 */
"""


def tokens():
    s = PAGE.read_text("utf-8")
    m = re.search(r"/\* tokens:start[^\n]*\n(.*?)\n[ \t]*/\* tokens:end \*/", s, re.S)
    if not m:
        sys.exit("tokens markers not found in assets/coach.html")
    lines = m.group(1).split("\n")
    return HEAD + "\n".join(l[2:] if l.startswith("  ") else l for l in lines).rstrip() + "\n"


if __name__ == "__main__":
    text = tokens()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text("utf-8") == text
        print("design/tokens.css is up to date" if ok else "design/tokens.css is out of date: run scripts/export_tokens.py")
        sys.exit(0 if ok else 1)
    OUT.write_text(text, "utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
