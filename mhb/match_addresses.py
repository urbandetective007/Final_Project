#!/usr/bin/env python3
"""Find directory entries whose address matches an address from the arnona list.

Usage: match_addresses.py PAGES_DIR ADDRESSES (xlsx: first column | txt: one per line) OUT.json

The directory text comes out in jumbled right-to-left order, so entries are not parsed here.
We only look for "<house number> <street>" (or "<street> <house number>") next to each other
and return the surrounding text; the agent then reads the snippet and extracts the business
name, category and phone, and verifies it.
"""
import json
import re
import sys
from pathlib import Path

CTX = 160  # characters of context on each side of a match


def norm(s: str) -> str:
    s = re.sub(r"[׳״'\"`’”]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def split_address(addr: str):
    """'דרך חברון 42א, ירושלים' -> ('דרך חברון', '42', 'א'); None if no house number."""
    a = norm(addr)
    a = re.sub(r"[,\-]?\s*ירושלים\s*$", "", a).strip(" ,")
    m = re.match(r"^(.*?)[\s,]+(\d{1,3})\s*([א-ת]?)$", a)
    if not m:
        return None
    return m.group(1).strip(" ,"), m.group(2), m.group(3)


def build_regexes(street: str, num: str, letter: str):
    st = re.escape(street).replace(r"\ ", r"\s+")
    lt = letter if letter else ""
    n = rf"(?<![\d\-]){num}{lt}(?!\d)"
    # letter-less addresses must not swallow a following Hebrew letter ("6א")
    if not letter:
        n = rf"(?<![\d\-]){num}(?![\dא-ת])"
    # words are often glued together in the extracted text ("החבצלתבלוי"), so no boundary
    # after the street; matches followed by a letter are flagged "glued" for verification
    s = rf"(?<![א-ת]){st}"
    return [("number-street", re.compile(rf"{n}\s+{s}")), ("street-number", re.compile(rf"{s}\s+{n}"))]


def load_addresses(path: str):
    p = Path(path)
    if p.suffix == ".xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(p, read_only=True).active
        vals = [r[0] for r in ws.iter_rows(values_only=True) if r and r[0]]
    else:
        vals = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [str(v).strip() for v in vals]


def main() -> None:
    pages_dir, addr_path, out = sys.argv[1:4]
    pages = {int(f.stem): f.read_text(encoding="utf-8") for f in Path(pages_dir).glob("*.txt")}
    hits, skipped = [], 0
    for addr in dict.fromkeys(load_addresses(addr_path)):
        parts = split_address(addr)
        if not parts:
            skipped += 1
            continue
        regs = build_regexes(*parts)
        for n, text in sorted(pages.items()):
            for order, rx in regs:
                for m in rx.finditer(text):
                    nxt = text[m.end(): m.end() + 1]
                    hits.append({
                        "address": addr, "page": n, "order": order,
                        "glued": bool(re.match(r"[א-ת]", nxt)),
                        "url": f"https://mhb.co.il/magazine2026/{n}/",
                        "snippet": text[max(0, m.start() - CTX): m.end() + CTX].replace("\n", " "),
                    })
    Path(out).write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(hits)} candidate matches, {skipped} addresses without a house number skipped")


if __name__ == "__main__":
    main()
