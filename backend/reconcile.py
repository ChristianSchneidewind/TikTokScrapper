# backend/reconcile.py
from .utils import _norm_text, _norm_user, safe_int

def cid_from_api_comment(c: dict):
    for key in ("cid", "cid_str", "id", "comment_id", "comment_id_str"):
        v = c.get(key)
        if v is not None and v != "0":
            return str(v)
    inner = c.get("comment") or {}
    for key in ("cid", "id", "comment_id"):
        v = inner.get(key)
        if v is not None and v != "0":
            return str(v)
    seed = f"{c.get('text','')}|{c.get('create_time','')}|{(c.get('user') or {}).get('unique_id','')}"
    import hashlib
    return "api_" + hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]

def user_from_api_comment(c) -> str | None:
    if isinstance(c, str):
        return c.strip() or None
    if not isinstance(c, dict):
        return None
    def pull(u):
        if isinstance(u, str):
            return u.strip() or None
        if isinstance(u, dict):
            for key in ("unique_id", "nickname", "uid", "short_id", "sec_uid"):
                v = u.get(key)
                if v:
                    return str(v)
        return None
    u = pull(c.get("user"))
    if u: return u
    inner = c.get("comment") or c.get("reply") or {}
    if isinstance(inner, dict):
        u = pull(inner.get("user"))
        if u: return u
    return None

def reconcile_cids_with_api(dom_comments, dom_replies_map, api_top, api_replies_map):
    def norm_key_full(cdict):
        return (_norm_user(user_from_api_comment(cdict)), safe_int(cdict.get("timestamp") or cdict.get("create_time")), _norm_text(cdict.get("text")))
    def norm_key_ts_text(cdict):
        return (safe_int(cdict.get("timestamp") or cdict.get("create_time")), _norm_text(cdict.get("text")))
    def _near(a,b,delta=60):  # 60s Toleranz
        return (a and b) and abs(int(a)-int(b)) <= delta

    api_top_by_full, api_top_by_ts_text, api_top_by_text = {}, {}, {}
    for c in api_top or []:
        if not isinstance(c, dict): continue
        api_top_by_full[norm_key_full(c)] = c
        api_top_by_ts_text[norm_key_ts_text(c)] = c
        api_top_by_text.setdefault(_norm_text(c.get("text")), []).append(c)

    api_rep_by_full, api_rep_by_ts_text, api_rep_by_text = {}, {}, {}
    for _, reps in (api_replies_map or {}).items():
        for r in reps or []:
            if not isinstance(r, dict): continue
            api_rep_by_full[norm_key_full(r)] = r
            api_rep_by_ts_text[norm_key_ts_text(r)] = r
            api_rep_by_text.setdefault(_norm_text(r.get("text")), []).append(r)

    def apply_from_api(dom_item, api_item):
        if not dom_item or not api_item: return
        cid_api = api_item.get("cid") or api_item.get("cid_str") or api_item.get("id") or api_item.get("comment_id")
        if cid_api and (not dom_item.get("cid") or str(dom_item.get("cid")).startswith("dom_")):
            dom_item["cid"] = str(cid_api)
        u_api = user_from_api_comment(api_item)
        if (not dom_item.get("user")) and u_api:
            dom_item["user"] = u_api
        if not safe_int(dom_item.get("timestamp")):
            ts_api = safe_int(api_item.get("timestamp") or api_item.get("create_time"))
            if ts_api: dom_item["timestamp"] = ts_api
        if dom_item.get("diggCount") in (None, 0) and safe_int(api_item.get("digg_count")):
            dom_item["diggCount"] = safe_int(api_item.get("digg_count"))
        if dom_item.get("replyCount") in (None, 0) and safe_int(api_item.get("reply_comment_total")):
            dom_item["replyCount"] = safe_int(api_item.get("reply_comment_total"))

    # Top-Level matchen (sicher → weich)
    for d in dom_comments or []:
        key_full = (_norm_user(d.get("user")), safe_int(d.get("timestamp")), _norm_text(d.get("text")))
        key_tt = (safe_int(d.get("timestamp")), _norm_text(d.get("text")))
        match = api_top_by_full.get(key_full) or api_top_by_ts_text.get(key_tt)
        if not match:
            same_text = api_top_by_text.get(_norm_text(d.get("text"))) or []
            cand = [c for c in same_text if _near(safe_int(d.get("timestamp")), safe_int(c.get("timestamp") or c.get("create_time")))]
            if len(cand) == 1:
                match = cand[0]
        if match:
            apply_from_api(d, match)

    # Replies matchen
    for pid, reps in (dom_replies_map or {}).items():
        for r in reps or []:
            key_full = (_norm_user(r.get("user")), safe_int(r.get("timestamp")), _norm_text(r.get("text")))
            key_tt = (safe_int(r.get("timestamp")), _norm_text(r.get("text")))
            match = api_rep_by_full.get(key_full) or api_rep_by_ts_text.get(key_tt)
            if not match:
                same_text = api_rep_by_text.get(_norm_text(r.get("text"))) or []
                cand = [c for c in same_text if _near(safe_int(r.get("timestamp")), safe_int(c.get("timestamp") or c.get("create_time")))]
                if len(cand) == 1:
                    match = cand[0]
            if match:
                apply_from_api(r, match)

def _key_by_identity(d: dict):
    return (_norm_user(d.get("user")), safe_int(d.get("timestamp")), _norm_text(d.get("text")))

def merge_dom_comments(a_list, b_list):
    best = {}
    for src in (a_list, b_list):
        for d in src:
            if not isinstance(d, dict):
                continue
            k = _key_by_identity(d)
            prev = best.get(k)
            if not prev:
                best[k] = d; continue
            prev_cid = str(prev.get("cid") or "")
            new_cid  = str(d.get("cid") or "")
            if prev_cid.startswith("dom_") and new_cid and not new_cid.startswith("dom_"):
                best[k] = d
            if (not best[k].get("user")) and d.get("user"):
                best[k]["user"] = d["user"]
            if (not best[k].get("timestamp")) and d.get("timestamp"):
                best[k]["timestamp"] = d["timestamp"]
    # Wichtig: DOM-only nicht verwerfen
    return list(best.values())

def merge_reply_maps(a_map, b_map):
    out = {}
    for src in (a_map, b_map):
        for pid, reps in (src or {}).items():
            bucket = out.setdefault(str(pid), [])
            seen = { _key_by_identity(r): r for r in bucket if isinstance(r, dict) }
            for r in reps:
                if not isinstance(r, dict):
                    continue
                k = _key_by_identity(r)
                prev = seen.get(k)
                if not prev:
                    seen[k] = r; bucket.append(r); continue
                prev_cid = str(prev.get("cid") or "")
                new_cid  = str(r.get("cid") or "")
                if prev_cid.startswith("dom_") and new_cid and not new_cid.startswith("dom_"):
                    idx = bucket.index(prev); bucket[idx] = r; seen[k] = r
    return out