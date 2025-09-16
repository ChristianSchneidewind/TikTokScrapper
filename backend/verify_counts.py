import json
import os
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _is_reply(row) -> bool:
    return bool(row.get("replyToCid"))

def _cid(x) -> str:
    v = (x.get("cid") if isinstance(x, dict) else x) or ""
    return str(v)

def _count_dom_cids(rows):
    return sum(1 for r in rows if str(r.get("cid","")).startswith("dom_"))

def verify_extraction(video_id: str):
    raw_path = os.path.join(BASE_DIR, f"raw_api_{video_id}.json")
    rows_path = os.path.join(BASE_DIR, f"comments_{video_id}.json")

    if not os.path.exists(raw_path):
        print(f"❌ Rohdaten fehlen: {raw_path}")
        return
    if not os.path.exists(rows_path):
        print(f"❌ Ergebnisdatei fehlt: {rows_path}")
        return

    raw = _load(raw_path)
    rows = _load(rows_path)

    api_flat = (raw.get("api_flat") or {})
    api_top = api_flat.get("top") or []                # Liste Top-Level-Kommentare (API)
    api_replies_map = api_flat.get("replies") or {}    # Dict parent_cid -> [replies]

    # ---- Zählung aus API ----
    api_top_count = len(api_top)
    api_reply_count = sum(len(v or []) for v in api_replies_map.values())
    api_total = api_top_count + api_reply_count

    # ---- Zählung aus rows ----
    rows_top = [r for r in rows if not _is_reply(r)]
    rows_replies = [r for r in rows if _is_reply(r)]
    rows_top_count = len(rows_top)
    rows_reply_count = len(rows_replies)
    rows_total = len(rows)

    print("=== Überblick =========================")
    print(f"API   Top-Level: {api_top_count:>4} | Replies: {api_reply_count:>4} | Summe: {api_total:>4}")
    print(f"ROWS  Top-Level: {rows_top_count:>4} | Replies: {rows_reply_count:>4} | Summe: {rows_total:>4}")

    # dom_* Diagnose
    dom_left = _count_dom_cids(rows)
    if dom_left:
        print(f"\nℹ️  dom_* CIDs in rows: {dom_left} (Fuzzy/DOM-Fallback noch aktiv)")

    # ---- Parent-Deckung prüfen (welche Parents fehlen völlig?) ----
    api_parent_cids = set(_cid(p) for p in api_replies_map.keys())
    rows_parent_cids = set(_cid(r.get("cid")) for r in rows_top)
    missing_parents = sorted(api_parent_cids - rows_parent_cids)

    if missing_parents:
        print("\n⚠️  Parents mit Replies, die in ROWS fehlen (gar kein Top-Level-Item gefunden):")
        for pid in missing_parents[:50]:
            print(f"  - {pid}  (API replies: {len(api_replies_map.get(pid, []))})")
        if len(missing_parents) > 50:
            print(f"  … und {len(missing_parents)-50} weitere")

    # ---- Reply-Deckung pro Parent prüfen ----
    # Map rows: parent_cid -> count(replies)
    rows_reply_by_parent = Counter()
    for r in rows_replies:
        rows_reply_by_parent[_cid(r.get("replyToCid"))] += 1

    lacking = []   # (parent, api_count, rows_count)
    for parent, api_list in api_replies_map.items():
        api_cnt = len(api_list or [])
        rows_cnt = rows_reply_by_parent.get(_cid(parent), 0)
        if rows_cnt < api_cnt:
            lacking.append((str(parent), api_cnt, rows_cnt))

    if lacking:
        lacking.sort(key=lambda x: (x[1]-x[2]), reverse=True)
        print("\n⚠️  Parents mit fehlenden Replies (API > ROWS):")
        for parent, api_cnt, rows_cnt in lacking[:50]:
            print(f"  - {parent}: API={api_cnt}  ROWS={rows_cnt}  (Fehlen: {api_cnt-rows_cnt})")
        if len(lacking) > 50:
            print(f"  … und {len(lacking)-50} weitere")

    # ---- Optional: Top-Level-Deckung (selten ein Problem, aber zur Vollständigkeit) ----
    api_top_cids = set(_cid(c) for c in api_top)
    rows_top_cids = set(_cid(r) for r in rows_top)
    missing_top = sorted(api_top_cids - rows_top_cids)
    if missing_top:
        print("\n⚠️  Top-Level-Kommentare fehlen in ROWS (gegenüber API):")
        for cid in missing_top[:50]:
            print(f"  - {cid}")
        if len(missing_top) > 50:
            print(f"  … und {len(missing_top)-50} weitere")

    # Schlussmeldung
    print("\n✅ Prüfung fertig.")

if __name__ == "__main__":
    # Beispiel: verify_extraction("7537358114467679510")
    import sys
    if len(sys.argv) != 2:
        print("Usage: python verify_counts.py <VIDEO_ID>")
        sys.exit(1)
    verify_extraction(sys.argv[1])