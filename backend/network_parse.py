# backend/network_parse.py
import base64, json, os, time, zlib
from urllib.parse import urlparse, parse_qs
from .config import logger, BACKEND_DIR

def harvest_comment_bodies(driver, perf_logs, aweme_id_filter: str | None = None):
    bodies, seen_req = [], set()
    debug_dir = os.path.join(BACKEND_DIR, "debug_comment_bodies")
    os.makedirs(debug_dir, exist_ok=True)
    debug_written = 0

    for e in perf_logs:
        try:
            msg = json.loads(e["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.responseReceived":
            continue
        params = msg.get("params", {})
        url = params.get("response", {}).get("url", "")
        if "/api/comment/list/" not in url:
            continue
        req_id = params.get("requestId")
        if not req_id or req_id in seen_req:
            continue
        seen_req.add(req_id)
        try:
            rb = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
            body = rb.get("body", "")
            if rb.get("base64Encoded"):
                body_bytes = base64.b64decode(body)
                try:
                    body_bytes = zlib.decompress(body_bytes, 16 + zlib.MAX_WBITS)
                except zlib.error:
                    pass
                body = body_bytes.decode("utf-8", errors="replace")
            data = json.loads(body)
        except Exception:
            continue

        try:
            aweme_id = str(data.get("aweme_id") or data.get("awemeId") or (data.get("aweme") or {}).get("aweme_id") or "")
        except Exception:
            aweme_id = ""
        if aweme_id_filter and aweme_id and aweme_id != str(aweme_id_filter):
            continue

        if debug_written < 5:
            any_missing = any(
                not (c.get("cid") or c.get("cid_str") or c.get("id") or c.get("comment_id") or (c.get("comment") or {}).get("cid"))
                for c in (data.get("comments") or [])
            )
            if any_missing:
                fn = os.path.join(debug_dir, f"{int(time.time())}_{req_id}.json")
                try:
                    with open(fn, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    debug_written += 1
                except Exception:
                    pass

        qs = parse_qs(urlparse(url).query)
        pid = (qs.get("comment_id") or [None])[0]
        bodies.append((pid, data))
    return bodies

def fetch_first_comment_page_via_js(driver, aweme_id: str, count: int = 100, sort_type: int = 0):
    script = r"""
        const done = arguments[0], vid = arguments[1], count = arguments[2], sortType = arguments[3];
        (async () => {
            try {
                const params = new URLSearchParams({
                    aweme_id: String(vid),
                    count: String(count || 100),
                    cursor: "0",
                    sort_type: String(sortType || 0)
                });
                const res = await fetch("/api/comment/list/?" + params.toString(), { credentials: "include" });
                const json = await res.json().catch(()=>({}));
                done({ ok: true, data: json });
            } catch (e) {
                done({ ok: false, err: String(e) });
            }
        })();
    """
    try:
        res = driver.execute_async_script(script, aweme_id, count, sort_type)
        if isinstance(res, dict) and res.get("ok") and isinstance(res.get("data"), dict):
            return res["data"]
    except Exception:
        pass
    return None