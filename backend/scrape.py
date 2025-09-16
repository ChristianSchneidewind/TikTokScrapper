# backend/scrape.py
import json, os, re, time, random
from selenium.webdriver.support.ui import WebDriverWait
from .config import logger
from .dom_parse import (
    set_comment_sort_newest, parse_comments_from_dom,
    expand_ui_replies, fully_load_comments, hydrate_first_comments,
    scroll_comments_area, ensure_comments_panel_open, dismiss_overlays,
    wait_for_initial_comments, sweep_virtualized_window,
    # ✨ NEU für Debug-Fallback:
    dump_comment_samples, diagnose_page_state
)
from .network_parse import harvest_comment_bodies, fetch_first_comment_page_via_js
from .reconcile import (
    reconcile_cids_with_api, merge_dom_comments, merge_reply_maps,
    cid_from_api_comment, user_from_api_comment
)
from .screenshots import screenshot_comments_and_replies
from .auth import _has_session, ensure_logged_in
from .utils import count_dom_cids, safe_int


def scrape_comments(driver, video_url, output_file, scroll_pause=0.8, take_screenshots=True):
    if not _has_session(driver):
        logger.warning("Session verloren – versuche Re-Login.")
        if not ensure_logged_in(driver):
            raise RuntimeError("Kein Login – Abbruch für dieses Video.")

    driver.get(video_url)
    # DOM ready
    try:
        WebDriverWait(driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:
        pass
    time.sleep(1.0)

    # Overlays + Panel
    dismiss_overlays(driver)
    if not ensure_comments_panel_open(driver):
        scroll_comments_area(driver, times=2, pause=0.2)
        dismiss_overlays(driver)
        ensure_comments_panel_open(driver)

    # Warten bis wirklich erste Kommentare sichtbar sind
    wait_for_initial_comments(driver, timeout=14)

    vid_match = re.search(r"/video/(\d+)", video_url)
    aweme_id_filter = vid_match.group(1) if vid_match else None

    # Sortierung auf "Neueste", wenn UI vorhanden
    set_comment_sort_newest(driver)

    # Frühe DOM-Probe
    dom_comments_early, dom_replies_early = parse_comments_from_dom(driver)

    all_logs, seen_msgs = [], set()
    def collect():
        try:
            for e in driver.get_log("performance"):
                m = e.get("message")
                if m in seen_msgs: 
                    continue
                seen_msgs.add(m)
                all_logs.append(e)
        except Exception:
            pass

    # Initiales Laden & Scrollen
    for _ in range(12):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        scroll_comments_area(driver, times=3, pause=scroll_pause * 0.4)
        time.sleep(random.uniform(scroll_pause * 0.7, scroll_pause * 1.3))

    collect()
    fully_load_comments(driver, scroll_pause=scroll_pause, max_cycles=18)
    collect()

    # Replies expandieren
    while True:
        clicks = expand_ui_replies(driver)
        collect()
        if clicks == 0:
            break
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(0.4)
        fully_load_comments(driver, scroll_pause=scroll_pause, max_cycles=6)
        collect()

    hydrate_first_comments(driver, max_items=200, pause=0.08)

    # Anti-Virtualisierung vor dem finalen DOM-Read
    sweep_virtualized_window(driver, sweeps=8, step_ratio=0.3, pause=0.18)

    dom_comments_late, dom_replies_late = parse_comments_from_dom(driver)
    dom_comments = merge_dom_comments(dom_comments_early, dom_comments_late)
    dom_replies  = merge_reply_maps(dom_replies_early, dom_replies_late)

    pid_bodies = harvest_comment_bodies(driver, all_logs, aweme_id_filter=aweme_id_filter)

    js_first = None
    if aweme_id_filter:
        js_first = fetch_first_comment_page_via_js(driver, aweme_id_filter, count=100, sort_type=0)
        if isinstance(js_first, dict) and (js_first.get("comments") or []):
            pid_bodies.insert(0, (None, js_first))

    # ---------------------- Fallback wenn (noch) nichts gefunden ----------------------
    def nothing_found():
        no_dom = (len(dom_comments) == 0 and sum(len(v) for v in dom_replies.values()) == 0)
        no_api = (sum(len((d or {}).get("comments") or []) for _pid, d in pid_bodies) == 0)
        return no_dom and no_api

    if nothing_found():
        logger.info("🔁 Fallback: Panel erneut öffnen, sweep & neu sammeln …")
        dismiss_overlays(driver)
        ensure_comments_panel_open(driver, timeout=6)
        wait_for_initial_comments(driver, timeout=10)
        sweep_virtualized_window(driver, sweeps=6, step_ratio=0.25, pause=0.15)
        collect()
        dom_comments2, dom_replies2 = parse_comments_from_dom(driver)
        if dom_comments2:
            dom_comments = merge_dom_comments(dom_comments, dom_comments2)
        if dom_replies2:
            dom_replies = merge_reply_maps(dom_replies, dom_replies2)
        pid_bodies2 = harvest_comment_bodies(driver, all_logs, aweme_id_filter=aweme_id_filter)
        if pid_bodies2:
            pid_bodies = pid_bodies2

    # ---------------------- normaler Fortgang ----------------------
    stagnant_rounds = 0
    for _ in range(20):
        def _has_more(bodies):
            for _pid, data in bodies:
                if data.get("has_more") in (1, True): return True
                if data.get("has_more_reply") in (1, True): return True
                cur = data.get("cursor") or data.get("next_cursor")
                if isinstance(cur, int) and cur > 0: return True
            return False

        if not _has_more(pid_bodies):
            break
        fully_load_comments(driver, scroll_pause=scroll_pause, max_cycles=8)
        expand_ui_replies(driver, max_clicks=80)
        collect()
        new_bodies = harvest_comment_bodies(driver, all_logs, aweme_id_filter=aweme_id_filter)
        if js_first and (None, js_first) not in new_bodies:
            new_bodies.insert(0, (None, js_first))
        stagnant_rounds = stagnant_rounds + 1 if len(new_bodies) == len(pid_bodies) else 0
        pid_bodies = new_bodies
        if stagnant_rounds >= 2:
            break

    # API → normalisieren
    comments_api, replies_map_api, seen_cids = [], {}, set()
    for pid, data in pid_bodies:
        for c in (data.get("comments") or []):
            cid = cid_from_api_comment(c)
            if not cid or cid in seen_cids:
                continue
            seen_cids.add(cid)
            d = {
                "cid": cid,
                "user": user_from_api_comment(c),
                "text": c.get("text"),
                "timestamp": safe_int(c.get("create_time")),
                "diggCount": safe_int(c.get("digg_count")),
                "replyCount": safe_int(c.get("reply_comment_total", 0)),
                "_source": "api",
            }
            parent_id = pid or c.get("reply_to_comment_id") or (c.get("comment") or {}).get("reply_to_comment_id")
            (replies_map_api.setdefault(str(parent_id), []).append(d)) if parent_id else comments_api.append(d)

    # Reconcile
    reconcile_cids_with_api(dom_comments, dom_replies, comments_api, replies_map_api)

    dom_set   = {str(d["cid"]) for d in dom_comments if d.get("cid")}
    final_top = dom_comments + [c for c in comments_api if str(c["cid"]) not in dom_set]

    # Flatten Rows
    rows = []
    for com in final_top:
        parent_cid = str(com["cid"])
        rows.append({
            "cid": parent_cid, "user": com["user"], "text": com["text"],
            "timestamp": com["timestamp"], "diggCount": com.get("diggCount"),
            "replyCount": com.get("replyCount", 0), "_source": com.get("_source")
        })
        reps = (dom_replies.get(parent_cid, []) + replies_map_api.get(parent_cid, []))
        for rep in reps:
            rows.append({
                "cid": str(rep["cid"]), "replyToCid": parent_cid, "user": rep["user"], "text": rep["text"],
                "timestamp": rep["timestamp"], "diggCount": rep.get("diggCount"),
                "replyCount": rep.get("replyCount", 0), "_source": rep.get("_source")
            })

    remaining_dom = count_dom_cids(rows)
    if remaining_dom:
        logger.info(f"ℹ️ {remaining_dom} Einträge mit dom_* CID.")

    # ✨ NEU: Wenn trotz allem keine Rows gefunden wurden → Diagnose + DOM-Samples
    if not rows:
        try:
            diagnose_page_state(driver, tag="after_build_rows_empty")
        except Exception:
            pass
        try:
            dump_comment_samples(driver, limit=5, tag="after_build_rows_empty")
        except Exception:
            pass

    # Screenshots
    if take_screenshots and rows:
        vid = aweme_id_filter or os.path.splitext(os.path.basename(output_file))[0].split("_")[-1]
        screenshot_comments_and_replies(driver, vid, rows)

    # Schreiben
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    logger.info(f"{len(rows)} Einträge → {output_file}")