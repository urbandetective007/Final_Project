#!/usr/bin/env python3
"""Download pages of the Haredi Guide Jerusalem directory (mhb.co.il) and save their text.

Usage: fetch_pages.py OUT_DIR [FIRST] [LAST]
Each page is saved as OUT_DIR/<N>.txt. Pages already present are skipped (resume).
"""
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

URL = "https://mhb.co.il/magazine2026/{n}/"
UA = "Mozilla/5.0 (compatible; arnona-agent/1.0)"


def page_text(raw: str) -> str:
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S)
    raw = re.sub(r"<[^>]+>", "\n", raw)
    lines = [l.strip() for l in html.unescape(raw).split("\n") if l.strip()]
    return "\n".join(lines)


def fetch(n: int, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL.format(n=n), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"page {n} failed")


def main() -> None:
    out = Path(sys.argv[1])
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 510
    out.mkdir(parents=True, exist_ok=True)
    for n in range(first, last + 1):
        f = out / f"{n}.txt"
        if f.exists():
            continue
        try:
            f.write_text(page_text(fetch(n)), encoding="utf-8")
        except RuntimeError as e:
            print(e, file=sys.stderr)
        time.sleep(0.5)  # be polite to the site
    print("done")


if __name__ == "__main__":
    main()
