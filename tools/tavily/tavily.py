#!/usr/bin/env python3
"""Tavily דרך API עם כמה מפתחות — עובר אוטומטית למפתח הבא כשהמכסה של מפתח נגמרת.

  status                          → כמה קרדיט נשאר בכל מפתח ובסה"כ (קוד יציאה 3 אם כולם גמורים)
  search "<שאילתה>" [--max-results N] [--depth ...] [--include-domains ...] [--exclude-domains ...] ...
  extract <url> [<url> ...] [--query "<שאילתה>"] → תוכן הדפים (raw_content)

המפתחות נקראים ממשתנה הסביבה TAVILY_API_KEYS (מופרדים בפסיק / רווח / שורה חדשה),
או TAVILY_API_KEY למפתח יחיד. המפתחות לעולם לא מודפסים — רק 4 התווים האחרונים.

החלפת מפתח:
  432 / 433 (מכסה נגמרה) או 401 (מפתח לא תקין) → המפתח מסומן כגמור, עוברים לבא ושולחים שוב את אותה בקשה.
  429 (יותר מדי בקשות) / 5xx / תקלת רשת → המתנה ונסיון חוזר עם אותו מפתח.
המפתח שעובד נשמר בקובץ מצב (TAVILY_STATE_FILE, ברירת מחדל ‎/tmp/tavily_keys_state.json),
כך שהקריאה הבאה באותה ריצה מתחילה ממנו ולא מבזבזת בקשות על מפתחות גמורים.

הפרמטרים וברירות המחדל זהים ל-Connector הרשמי (tavily-mcp): נשלח רק מה שצוין, והשאר לפי ברירת המחדל של Tavily.
התוכן המחולץ מוחזר במלואו, בלי קיצור.

פלט: JSON ל-stdout, הודעות ל-stderr. קודי יציאה: 0 תקין · 1 שגיאה · 2 אין מפתחות · 3 כל המפתחות גמורים.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("TAVILY_API_BASE", "https://api.tavily.com").rstrip("/")
STATE_FILE = os.environ.get("TAVILY_STATE_FILE", "/tmp/tavily_keys_state.json")

EXHAUSTED_CODES = {432, 433}   # מכסת התוכנית / מכסת pay-as-you-go נגמרה
INVALID_CODES = {401}
RETRY_CODES = {429, 500, 502, 503, 504}
RETRY_WAITS = [2, 5, 15]       # שניות בין נסיונות חוזרים עם אותו מפתח

EXIT_ERROR, EXIT_NO_KEYS, EXIT_ALL_EXHAUSTED = 1, 2, 3


class AllKeysExhausted(Exception):
    pass


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_keys():
    raw = os.environ.get("TAVILY_API_KEYS") or os.environ.get("TAVILY_API_KEY") or ""
    keys = [k for k in re.split(r"[\s,;]+", raw) if k]
    return list(dict.fromkeys(keys))


def mask(key):
    return f"…{key[-4:]}"


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def http(method, path, key, body=None, timeout=60):
    """(status, parsed JSON or text, Retry-After seconds or None). A network failure is status 0."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, text, headers = resp.status, resp.read().decode("utf-8", "replace"), resp.headers
    except urllib.error.HTTPError as e:
        status, text, headers = e.code, e.read().decode("utf-8", "replace"), e.headers
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, str(e), None
    retry_after = headers.get("Retry-After") if headers else None
    retry_after = int(retry_after) if retry_after and retry_after.isdigit() else None
    try:
        return status, json.loads(text), retry_after
    except ValueError:
        return status, text, retry_after


def call(path, body):
    """POST to Tavily, rotating to the next key when one is used up or invalid."""
    keys = load_keys()
    if not keys:
        log("❌ לא הוגדרו מפתחות — יש להגדיר את משתנה הסביבה TAVILY_API_KEYS")
        sys.exit(EXIT_NO_KEYS)
    state = load_state()
    dead = set(state.get("dead", []))
    start = state.get("current", 0) % len(keys)
    order = keys[start:] + keys[:start]

    for key in order:
        if mask(key) in dead:
            continue
        for attempt in range(len(RETRY_WAITS) + 1):
            status, payload, retry_after = http("POST", path, key, body)
            if status == 200:
                state["current"] = keys.index(key)
                save_state(state)
                return payload
            if status in EXHAUSTED_CODES or status in INVALID_CODES:
                reason = "המכסה נגמרה" if status in EXHAUSTED_CODES else "מפתח לא תקין"
                log(f"⚠️ מפתח {mask(key)}: {reason} ({status}) — עובר למפתח הבא")
                dead.add(mask(key))
                state["dead"] = sorted(dead)
                save_state(state)
                break
            if (status in RETRY_CODES or status == 0) and attempt < len(RETRY_WAITS):
                wait = min(retry_after or RETRY_WAITS[attempt], 60)
                log(f"⏳ מפתח {mask(key)}: {status or 'תקלת רשת'} — נסיון חוזר בעוד {wait} שניות")
                time.sleep(wait)
                continue
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            raise RuntimeError(f"Tavily {path} נכשל ({status}): {str(detail)[:300]}")
    raise AllKeysExhausted()


def key_usage(key):
    """(used, limit) for a key, or None if Tavily doesn't say."""
    status, payload, _ = http("GET", "/usage", key, timeout=30)
    if status in EXHAUSTED_CODES:
        return "exhausted"
    if status in INVALID_CODES:
        return "invalid"
    if status != 200 or not isinstance(payload, dict):
        return None
    # A key with its own cap reports it; otherwise the account's plan is the cap.
    k = payload.get("key") or {}
    acc = payload.get("account") or {}
    if k.get("limit") is not None:
        used, limit = k.get("usage"), k.get("limit")
    else:
        used, limit = acc.get("plan_usage"), acc.get("plan_limit")
    if used is None or limit is None:
        return None
    return int(used), int(limit)


def cmd_status(_args):
    keys = load_keys()
    if not keys:
        log("❌ לא הוגדרו מפתחות — יש להגדיר את משתנה הסביבה TAVILY_API_KEYS")
        sys.exit(EXIT_NO_KEYS)
    rows, total_left, usable = [], 0, 0
    for key in keys:
        u = key_usage(key)
        if u == "exhausted":
            rows.append({"key": mask(key), "status": "exhausted", "remaining": 0})
        elif u == "invalid":
            rows.append({"key": mask(key), "status": "invalid", "remaining": 0})
        elif u is None:
            rows.append({"key": mask(key), "status": "unknown"})
            usable += 1
        else:
            used, limit = u
            left = max(0, limit - used)
            rows.append({"key": mask(key), "status": "ok" if left else "exhausted", "used": used, "limit": limit, "remaining": left})
            total_left += left
            usable += 1 if left else 0
    # Keys that are used up are skipped from the start of the run.
    save_state({"dead": [r["key"] for r in rows if r["status"] in ("exhausted", "invalid")], "current": 0})
    print(json.dumps({"keys": rows, "total_remaining": total_left, "usable_keys": usable}, ensure_ascii=False, indent=2))
    for r in rows:
        extra = f"{r['used']}/{r['limit']} — נשארו {r['remaining']}" if "limit" in r else ""
        log(f"  {r['key']}: {r['status']} {extra}")
    log(f'סה"כ קרדיט שנשאר: {total_left} · מפתחות שמישים: {usable}/{len(keys)}')
    if usable == 0:
        sys.exit(EXIT_ALL_EXHAUSTED)


# Same parameters and defaults as the official Tavily MCP connector (tavily-mcp):
# only what was given is sent, so Tavily's own defaults apply to the rest.
SEARCH_OPTIONS = ["search_depth", "topic", "time_range", "start_date", "end_date", "max_results",
                  "include_raw_content", "include_images", "include_domains", "exclude_domains", "country", "exact_match"]


def options(args, names):
    return {n: getattr(args, n) for n in names if getattr(args, n) not in (None, False, [])}


def cmd_search(args):
    body = {"query": args.query, **options(args, SEARCH_OPTIONS)}
    if body.get("country"):
        body["topic"] = "general"          # as the connector does
    if body.get("start_date") or body.get("end_date"):
        body.pop("time_range", None)       # as the connector does
    res = call("/search", body)
    out = []
    for r in res.get("results", []):
        item = {"title": r.get("title"), "url": r.get("url"), "content": r.get("content"), "score": r.get("score")}
        if r.get("raw_content"):
            item["raw_content"] = r["raw_content"]
        out.append(item)
    result = {"query": args.query, "results": out}
    if res.get("images"):
        result["images"] = res["images"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_extract(args):
    body = {"urls": args.urls, **options(args, ["extract_depth", "format", "include_images", "query"])}
    res = call("/extract", body)
    out = []
    for r in res.get("results", []):
        item = {"url": r.get("url"), "raw_content": r.get("raw_content") or ""}
        if r.get("images"):
            item["images"] = r["images"]
        out.append(item)
    failed = [f if isinstance(f, dict) else {"url": f} for f in res.get("failed_results", [])]
    print(json.dumps({"results": out, "failed": failed}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--max-results", dest="max_results", type=int, help="5–20 (ברירת מחדל של Tavily: 5)")
    s.add_argument("--depth", dest="search_depth", choices=["basic", "advanced", "fast", "ultra-fast"])
    s.add_argument("--topic", choices=["general", "news"])
    s.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"])
    s.add_argument("--start-date", dest="start_date", help="YYYY-MM-DD")
    s.add_argument("--end-date", dest="end_date", help="YYYY-MM-DD")
    s.add_argument("--include-domains", dest="include_domains", nargs="+")
    s.add_argument("--exclude-domains", dest="exclude_domains", nargs="+")
    s.add_argument("--country", help="שם מדינה מלא, למשל israel")
    s.add_argument("--include-raw-content", dest="include_raw_content", action="store_true")
    s.add_argument("--include-images", dest="include_images", action="store_true")
    s.add_argument("--exact-match", dest="exact_match", action="store_true")
    s.set_defaults(func=cmd_search)
    e = sub.add_parser("extract")
    e.add_argument("urls", nargs="+")
    e.add_argument("--query", help="מחזיר רק את קטעי הדף הרלוונטיים לשאילתה")
    e.add_argument("--depth", dest="extract_depth", choices=["basic", "advanced"])
    e.add_argument("--format", choices=["markdown", "text"])
    e.add_argument("--include-images", dest="include_images", action="store_true")
    e.set_defaults(func=cmd_extract)
    args = p.parse_args()
    try:
        args.func(args)
    except AllKeysExhausted:
        log("⛔ כל מפתחות Tavily גמורים — אין קרדיט לחיפוש")
        sys.exit(EXIT_ALL_EXHAUSTED)
    except RuntimeError as e:
        log(f"❌ {e}")
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()
