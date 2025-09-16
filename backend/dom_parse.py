# backend/dom_parse.py
import time
import random
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import logger
from .selectors import SEL


# ------------------------------------------------------------
# Replies expandieren (einmal pro Stelle) + optionaler Scope
# ------------------------------------------------------------

# Wiederverwendungs-Speicher über Render-Zyklen hinweg
_CLICKED_SIGNATURES = set()

def expand_ui_replies(driver, max_clicks=300, scope_comments_only=True):
    """
    Klickt 'Antworten anzeigen' / 'Mehr anzeigen' Buttons.
    - Markiert geklickte Elemente: data-clicked-reply-expander="1"
    - Vermeidet Wiederholungen via Signatur (text_snip + parent_cid + yBucket)
    - scope_comments_only=True: nur Buttons innerhalb der Kommentarlisten
    """
    def is_view_replies(el):
        try:
            t = (el.text or "").strip().lower()
        except Exception:
            return False
        # robustes Matching (DE/EN)
        return bool(re.search(
            r"(view\s+\d*\s*repl(y|ies)|antworten anzeigen|weitere antworten|mehr anzeigen)",
            t
        ))

    def element_signature(el):
        """Signatur: (text_snip, parent_cid, yBucket)"""
        try:
            sig = driver.execute_script("""
                const el = arguments[0];
                function closestContainer(node){
                  return node.closest("div[data-e2e='comment-item'],div[class*='DivCommentItemWrapper'],li[data-e2e*='comment'],div[class*='comment'][class*='item']");
                }
                const cont = closestContainer(el) || document.body;
                const cid = cont.getAttribute('data-cid') || cont.getAttribute('data-comment-id')
                           || cont.getAttribute('data-e2e-cid') || cont.getAttribute('data-id') || '';
                const rect = el.getBoundingClientRect();
                const y = Math.round(rect.top/20)*20; // Bucket
                const txt = (el.textContent || "").trim().toLowerCase().replace(/\s+/g, " ").slice(0,80);
                return [txt, cid, y].join("|");
            """, el)
            return sig or ""
        except Exception:
            return ""

    clicks = 0
    cycles_without_progress = 0

    # optional auf Kommentarlisten einschränken
    base_nodes = []
    if scope_comments_only:
        try:
            base_nodes = driver.find_elements(
                By.CSS_SELECTOR,
                "div[data-e2e='comment-list'],div[data-e2e='browse-comment-list'],div[data-e2e='comment-scroll-list']"
            )
        except Exception:
            base_nodes = []

    while clicks < max_clicks and cycles_without_progress < 3:
        # Kandidaten suchen
        try:
            found = driver.find_elements(*SEL["reply_expand"]) or []
        except Exception:
            found = []

        # Wenn nichts gefunden wurde, minimal scrollen (Materialize) und erneut prüfen
        if not found:
            try:
                h = driver.execute_script("return window.innerHeight || 900;")
            except Exception:
                h = 900
            step = max(120, int(h * 0.30))
            driver.execute_script("window.scrollBy(0, arguments[0]);", step)
            time.sleep(0.2)
            driver.execute_script("window.scrollBy(0, arguments[0]);", -step//2)
            time.sleep(0.2)
            try:
                found = driver.find_elements(*SEL["reply_expand"]) or []
            except Exception:
                found = []

        # ggf. auf Kommentar-Scope filtern
        if base_nodes:
            filtered_scope = []
            for el in found:
                try:
                    inside = driver.execute_script("""
                        const el = arguments[0], bases = arguments[1];
                        for (const b of bases){ if (b && b.contains(el)) return true; }
                        return false;
                    """, el, base_nodes)
                except Exception:
                    inside = True
                if inside:
                    filtered_scope.append(el)
            found = filtered_scope

        # filtern: echte Buttons, noch nicht geklickt, keine Editoren
        filtered = []
        for el in found:
            try:
                if el.get_attribute("data-clicked-reply-expander") == "1":
                    continue
                if not is_view_replies(el):
                    continue
                role = (el.get_attribute("role") or "").lower()
                datae2e = (el.get_attribute("data-e2e") or "").lower()
                if "reply-btn" in datae2e or role in ("textbox", "combobox"):
                    continue
                sig = element_signature(el)
                if sig and sig in _CLICKED_SIGNATURES:
                    continue
                el._shot_sig = sig
                filtered.append(el)
            except Exception:
                continue

        batch_clicks = 0
        for el in filtered:
            if clicks >= max_clicks:
                break
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                try:
                    WebDriverWait(driver, 3).until(EC.element_to_be_clickable(el))
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)
                driver.execute_script("arguments[0].setAttribute('data-clicked-reply-expander','1');", el)
                sig = getattr(el, "_shot_sig", "") or element_signature(el)
                if sig:
                    _CLICKED_SIGNATURES.add(sig)
                clicks += 1
                batch_clicks += 1
                time.sleep(random.uniform(0.25, 0.55))
            except Exception:
                continue

        if batch_clicks == 0:
            cycles_without_progress += 1
        else:
            cycles_without_progress = 0

        # Mini-Sweep, um neue Buttons zu materialisieren
        try:
            h = driver.execute_script("return window.innerHeight || 900;")
        except Exception:
            h = 900
        step = max(120, int(h * 0.35))
        driver.execute_script("window.scrollBy(0, arguments[0]);", step)
        time.sleep(0.18)
        driver.execute_script("window.scrollBy(0, arguments[0]);", -step//2)
        time.sleep(0.18)

    logger.info(f"View-replies Buttons geklickt: {clicks} (Abbrüche: {cycles_without_progress})")
    return clicks


# ------------------------------------------------------------
# Kommentare vollständig laden (Scroll + "Mehr Kommentare")
# ------------------------------------------------------------
# --- Kommentar-Sortierung: "Neueste zuerst" ---------------------------------
def set_comment_sort_newest(driver, timeout: float = 6.0) -> bool:
    """
    Stellt – falls vorhanden – die Kommentar-Sortierung auf 'Neueste'/'Newest'.
    Gibt True zurück, wenn ein Klick durchgeführt wurde (oder bereits korrekt).
    """
    import time
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from .config import logger

    def _lower(s): 
        return (s or "").strip().lower()

    # 1) Möglichen Sortier-Button öffnen
    # Häufig: data-e2e='comment-order' oder ein Button/Span/Div mit Sortier-Text
    openers_xpath = (
        "//*[@data-e2e='comment-order' or "
        "(self::button or self::span or self::div)"
        "[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'sortieren') or "
        " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sort') or "
        " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'neueste') or "
        " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newest')]]"
    )

    try:
        openers = driver.find_elements(By.XPATH, openers_xpath) or []
    except Exception:
        openers = []

    opened = False
    for el in openers:
        try:
            if not el.is_displayed():
                continue
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            try:
                WebDriverWait(driver, 2).until(EC.element_to_be_clickable(el))
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(0.3)
            opened = True
            break
        except Exception:
            continue

    # 2) Auswahl treffen: 'Neueste' / 'Newest' / 'New' etc.
    # Häufig als Menu/Popup gerendert
    options_xpath = (
        "//*[self::div or self::li or self::button or self::span or self::a]"
        "[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'neueste') or "
        " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'newest') or "
        " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'new')]"
    )

    clicked = False
    try:
        # kurz warten, falls Menü asynchron kommt
        WebDriverWait(driver, 2).until(lambda d: len(d.find_elements(By.XPATH, options_xpath)) > 0)
    except Exception:
        pass

    try:
        options = driver.find_elements(By.XPATH, options_xpath) or []
    except Exception:
        options = []

    for opt in options:
        try:
            txt = _lower(opt.text)
            # leichte Heuristik: bevorzuge eindeutig „neueste/newest“
            if "neueste" in txt or "newest" in txt or txt == "new":
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", opt)
                try:
                    WebDriverWait(driver, 2).until(EC.element_to_be_clickable(opt))
                    opt.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", opt)
                time.sleep(0.3)
                clicked = True
                break
        except Exception:
            continue

    if clicked:
        logger.info("✅ Kommentar-Sortierung: 'Neueste' ausgewählt.")
        return True

    if opened:
        logger.info("ℹ️ Sortiermenü gefunden, aber keine 'Neueste/Newest'-Option erkannt (evtl. bereits aktiv).")
        return True

    logger.info("ℹ️ Keine Kommentar-Sortierung gefunden (Layout ohne Sortier-UI).")
    return False

def fully_load_comments(driver, scroll_pause=0.8, max_cycles=6):
    """
    Scrollt durch den Kommentarbereich und klickt 'Mehr Kommentare' (falls vorhanden).
    Beendet, wenn sich die Anzahl der Kommentar-Container nicht mehr erhöht
    oder max_cycles erreicht ist.
    """
    def count_containers():
        try:
            return driver.execute_script("""
                return document.querySelectorAll(
                  "div[data-e2e='comment-item'],div[class*='DivCommentItemWrapper'],li[data-e2e*='comment'],div[class*='comment'][class*='item']"
                ).length;
            """) or 0
        except Exception:
            return 0

    def click_load_more():
        # Case-insensitive XPath für „Mehr Kommentare“ / „Load more comments“
        xpath = (
            "//*[self::button or self::a]"
            "[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'mehr kommentare')"
            " or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'load more comments')]"
        )
        try:
            btns = driver.find_elements(By.XPATH, xpath) or []
        except Exception:
            btns = []
        clicked = 0
        for b in btns:
            try:
                if not b.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                try:
                    WebDriverWait(driver, 3).until(EC.element_to_be_clickable(b))
                    b.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", b)
                clicked += 1
                time.sleep(0.4)
            except Exception:
                continue
        return clicked

    last_count = -1
    stagnant_rounds = 0

    for _ in range(max_cycles):
        # Scroll etwas runter und wieder hoch (Materialize)
        try:
            h = driver.execute_script("return window.innerHeight || 900;")
        except Exception:
            h = 900
        step = max(200, int(h * 0.6))
        driver.execute_script("window.scrollBy(0, arguments[0]);", step)
        time.sleep(scroll_pause)
        driver.execute_script("window.scrollBy(0, arguments[0]);", -step//2)
        time.sleep(0.2)

        # „Mehr Kommentare“ klicken, falls vorhanden
        lm = click_load_more()

        # zurück nach oben, damit Top-Items gemountet sind
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(0.2)

        cur = count_containers()
        if cur <= last_count and lm == 0:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        last_count = max(last_count, cur)

        if stagnant_rounds >= 2:
            break

    return last_count if last_count >= 0 else 0


# ------------------------------------------------------------
# Kommentare & Replies aus dem DOM sammeln
# ------------------------------------------------------------

def collect_rows(driver) -> list[dict]:
    """
    Sammelt Kommentare und Replies aus dem DOM.
    Robustere Selector-Varianten + textFallback, der Buttons/Controls ignoriert.
    """
    js = r"""
    (function(){
      function norm(s){ return (s||"").replace(/\s+/g," ").trim(); }

      // Hilfsfunktion: Entfern UI/Controls aus einem Knoten (im Memory, nicht im DOM)
      function stripUI(root){
        if (!root) return;
        const kill = root.querySelectorAll([
          // Buttons/Links/Interaktionen
          "button","a[role='button']","a[href^='javascript:']",
          // Icons/SVG
          "svg","use","path",
          // Zähler/Badges
          "[aria-hidden='true']",
          // Reply/Like-Leisten
          "[data-e2e*='like']","[data-e2e*='reply-btn']",
          // Zeit/Meta
          "time","[datetime]"
        ].join(","));
        kill.forEach(n => n.remove());

        // typische Phrasen in Textknoten maskieren
        function cleanTextNodes(node){
          node.childNodes.forEach(ch=>{
            if (ch.nodeType===3){ // Text
              ch.nodeValue = ch.nodeValue
                .replace(/\b(Mehr anzeigen|MEHR ANZEIGEN|mehr anzeigen|Antworten anzeigen|Weitere Antworten|View (more )?repl(y|ies)|Replies)\b/gi," ")
                .replace(/\b(Like|Gefällt mir|Antwort(en)?)\b/gi," ");
            } else if (ch.nodeType===1){
              cleanTextNodes(ch);
            }
          });
        }
        cleanTextNodes(root);
      }

      function pickTextFromCandidates(c, selectors){
        for (const sel of selectors){
          const n = c.querySelector(sel);
          if (n){
            const clone = n.cloneNode(true);
            stripUI(clone);
            const t = norm(clone.textContent||"");
            if (t) return t;
          }
        }
        return "";
      }

      function getUser(c){
        // alt & neu
        const userNode = c.querySelector(
          '[data-e2e="comment-username"],'
        + '[data-e2e="comment-user-uniqueid"],'
        + '[data-e2e="comment-username-text"],'
        + 'a[href^="/@"],a[href*="/@"]'
        );
        if (userNode){
          let t = norm(userNode.textContent||"");
          if (t) return t;
          const href = norm(userNode.getAttribute('href')||"");
          if (href.includes("/@")) return "@"+href.split("/@").pop().split(/[/?#]/)[0];
        }
        return "";
      }

      function getTs(c){
        const t = c.getAttribute("data-create-time") || c.getAttribute("data-time") || "";
        const n = parseInt(t, 10);
        if (!isNaN(n) && n>0) return n;
        const timeLike = c.querySelector("time,[datetime]");
        if (timeLike){
          const dt = timeLike.getAttribute("datetime") || timeLike.getAttribute("title") || "";
          const ms = Date.parse(dt);
          if (!isNaN(ms)) return Math.floor(ms/1000);
        }
        return 0;
      }

      function cidOf(c){
        return c.getAttribute("data-cid")
            || c.getAttribute("data-comment-id")
            || c.getAttribute("data-e2e-cid")
            || c.getAttribute("data-id")
            || "";
      }

      function textOf(c){
        // Priorisierte Targets
        const primarySelectors = [
          '[data-e2e="comment-text"]',
          '[data-e2e="reply-text"]',
          '[data-e2e="comment-content"]'
        ];
        let t = pickTextFromCandidates(c, primarySelectors);
        if (t) return t;

        // häufige generische Text-Container
        const secondarySelectors = [
          'span[dir]','div[dir]','p[dir]',
          'div[class*="text"]','span[class*="text"]'
        ];
        t = pickTextFromCandidates(c, secondarySelectors);
        if (t) return t;

        // Fallback: kompletter Container (kopiert), UI wegstrippen
        const clone = c.cloneNode(true);
        stripUI(clone);
        t = norm(clone.textContent||"");
        return t;
      }

      function hash64(s){
        let h1=0xdeadbeef ^ s.length, h2=0x41c6ce57 ^ s.length;
        for (let i=0;i<s.length;i++){
          const ch = s.charCodeAt(i);
          h1 = Math.imul(h1 ^ ch, 2654435761);
          h2 = Math.imul(h2 ^ ch, 1597334677);
        }
        h1 = (h1 ^ (h1>>>16)) >>> 0;
        h2 = (h2 ^ (h2>>>13)) >>> 0;
        return (h1>>>0).toString(16).padStart(8,"0") + (h2>>>0).toString(16).padStart(8,"0");
      }

      // Container (breiter gefasst, inkl. Level-Varianten)
      const containers = Array.from(document.querySelectorAll(
          "div[data-e2e='comment-item'],"
        + "div[class*='DivCommentItemWrapper'],"
        + "li[data-e2e*='comment'],"
        + "div[class*='comment'][class*='item'],"
        + "div[data-e2e='comment-level-1'],"
        + "div[data-e2e='comment-level-2']"
      ));

      const rows = [];
      for (const c of containers){
        const user = getUser(c);
        const text = textOf(c);
        const ts = getTs(c);

        // Filter jetzt relaxter: nimm Eintrag, wenn Text >= 2 Zeichen vorhanden ist
        if (!user && (!text || text.length < 2)) continue;

        let finalCid = cidOf(c);
        if (!finalCid){
          const key = (user.toLowerCase()||"")+"|"+(ts||0)+"|"+(text.toLowerCase()||"");
          finalCid = "dom_" + hash64(key);
        }

        rows.push({cid: finalCid, user, text, timestamp: ts});

        // Replies innerhalb des Containers
        const replyNodes = c.querySelectorAll(
            "div[data-e2e='comment-reply-item'],"
          + "li[data-e2e*='reply'],"
          + "div[class*='reply'][class*='item'],"
          + "div[data-e2e='comment-level-2']"
        );
        for (const r of replyNodes){
          const ruser = getUser(r);
          const rtext = textOf(r);
          const rts = getTs(r);
          if (!ruser && (!rtext || rtext.length < 2)) continue;

          let rfinal = cidOf(r);
          if (!rfinal){
            const rkey = (ruser.toLowerCase()||"")+"|"+(rts||0)+"|"+(rtext.toLowerCase()||"");
            rfinal = "dom_" + hash64(rkey);
          }
          rows.push({cid: rfinal, user: ruser, text: rtext, timestamp: rts, parent: finalCid});
        }
      }
      return rows;
    })();
    """
    try:
        data = driver.execute_script(js) or []
    except Exception:
        data = []

    out = []
    for it in data:
        if not isinstance(it, dict):
            continue
        row = {
            "cid": str(it.get("cid") or ""),
            "user": (it.get("user") or "").strip(),
            "text": (it.get("text") or "").strip(),
            "timestamp": int(it.get("timestamp") or 0),
        }
        if it.get("parent"):
            row["parent"] = str(it.get("parent"))
        out.append(row)
    return out


def dump_comment_samples(driver, limit: int = 5, tag: str = "sample"):
    """
    Speichert die outerHTML der ersten 'limit' Kommentar-Container in debug_dumps/*.html,
    damit man das tatsächliche Layout inspizieren kann.
    """
    import os, time, re
    from .config import logger

    htmls = driver.execute_script(r"""
      const nodes = Array.from(document.querySelectorAll(
          "div[data-e2e='comment-item'],"
        + "div[class*='DivCommentItemWrapper'],"
        + "li[data-e2e*='comment'],"
        + "div[class*='comment'][class*='item'],"
        + "div[data-e2e='comment-level-1'],"
        + "div[data-e2e='comment-level-2']"
      ));
      return nodes.slice(0, arguments[0]).map(n => n.outerHTML);
    """, int(limit)) or []

    try:
        os.makedirs("debug_dumps", exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join("debug_dumps", f"{ts}_{tag}_containers.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write("<!doctype html><meta charset='utf-8'><title>samples</title>\n")
            for i, h in enumerate(htmls, 1):
                f.write(f"<h3>Container {i}</h3>\n<div style='border:1px solid #ccc;padding:8px;margin:8px 0'>{h}</div>\n")
        logger.info("🧪 DOM-Samples gespeichert: %s", path)
    except Exception as e:
        logger.warning("Konnte DOM-Samples nicht speichern: %s", e)



# ------------------------------------------------------------
# Diagnose-Helfer
# ------------------------------------------------------------

def diagnose_page_state(driver, tag: str = "diag"):
    """
    Prüft die Seite auf typische Ursachen für '0 Kommentare':
    - URL/Path (Login-Redirect?)
    - Kommentar-Container / -Listen / Expand-Buttons
    - Overlays/Consent
    - iFrames
    - speichert einen Debug-Screenshot unter debug_dumps/
    """
    import os
    from selenium.webdriver.common.by import By

    try:
        href = driver.execute_script("return location.href;") or ""
        path = driver.execute_script("return location.pathname;") or ""
        title = driver.title or ""
    except Exception:
        href, path, title = "", "", ""

    # Kommentar-Container zählen
    try:
        container_count = driver.execute_script("""
            return document.querySelectorAll(
              "div[data-e2e='comment-item'],div[class*='DivCommentItemWrapper'],li[data-e2e*='comment'],div[class*='comment'][class*='item']"
            ).length;
        """) or 0
    except Exception:
        container_count = 0

    # Kommentarlisten vorhanden?
    try:
        lists = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-e2e='comment-list'],[data-e2e='browse-comment-list'],[data-e2e='comment-scroll-list']"
        )
        list_count = len(lists)
    except Exception:
        list_count = 0

    # Expand-Buttons zählen (gleiches SEL wie expand_ui_replies)
    try:
        expand_btns = driver.find_elements(*SEL["reply_expand"])
        expand_count = len(expand_btns)
    except Exception:
        expand_count = -1

    # Overlays/Consent grob prüfen
    def _find_text_nodes():
        try:
            return driver.find_elements(By.XPATH,
                "//*[self::button or self::a or self::div or self::span]["
                " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'zustimmen')"
                " or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')"
                " or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'ablehnen')"
                " or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'anmelden')"
                " or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'einloggen')"
                "]"
            )
        except Exception:
            return []
    overlay_hits = _find_text_nodes()
    overlay_count = len(overlay_hits)

    # iFrames?
    try:
        iframe_count = len(driver.find_elements(By.TAG_NAME, "iframe"))
    except Exception:
        iframe_count = -1

    # Debug-Screenshot
    try:
        os.makedirs("debug_dumps", exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (path or "video"))
        shot_path = os.path.join("debug_dumps", f"{ts}_{tag}_{safe}.png")
        driver.save_screenshot(shot_path)
    except Exception:
        shot_path = ""

    logger.info(
        "🔎 Diagnose %s | path=%s | containers=%s | lists=%s | expand=%s | overlays=%s | iframes=%s | shot=%s",
        tag, path, container_count, list_count, expand_count, overlay_count, iframe_count,
        shot_path.split("/")[-1] if shot_path else "-"
    )
    if "login" in (path or "").lower():
        logger.warning("⚠️  Vermutlich Login/Redirect aktiv (path enthält 'login').")

    return {
        "href": href, "path": path, "title": title,
        "comment_container_count": container_count,
        "comment_list_count": list_count,
        "expand_button_count": expand_count,
        "overlay_like_elements": overlay_count,
        "iframe_count": iframe_count,
        "debug_screenshot": shot_path,
    }

def parse_comments_from_dom(driver):
    """
    Liest mit collect_rows() alle Comments/Replies und trennt in:
      - dom_comments: List[dict] (Top-Level-Kommentare)
      - dom_replies:  Dict[parent_cid -> List[dict]] (Replies je Parent)
    """
    rows = collect_rows(driver)
    dom_comments, dom_replies = [], {}
    seen_top = set()

    # Top-Level = Einträge ohne "parent"
    for r in rows:
        if not r.get("parent"):
            cid = str(r.get("cid") or "")
            if cid and cid not in seen_top:
                seen_top.add(cid)
                dom_comments.append({
                    "cid": cid,
                    "user": (r.get("user") or "").strip(),
                    "text": (r.get("text") or "").strip(),
                    "timestamp": int(r.get("timestamp") or 0),
                    "_source": "dom",
                })

    # Replies = Einträge mit "parent"
    for r in rows:
        parent = r.get("parent")
        if not parent:
            continue
        parent = str(parent)
        lst = dom_replies.setdefault(parent, [])
        lst.append({
            "cid": str(r.get("cid") or ""),
            "user": (r.get("user") or "").strip(),
            "text": (r.get("text") or "").strip(),
            "timestamp": int(r.get("timestamp") or 0),
            "_source": "dom",
        })

    return dom_comments, dom_replies


def dismiss_overlays(driver):
    """
    Versucht, Cookies-/Overlay-Dialoge zu schließen (DE/EN Keys).
    Ist bewusst tolerant; Fehler sind egal.
    """
    from selenium.webdriver.common.by import By
    import time

    candidates = [
        # Buttons/Links mit typischen Texten
        ("//*[self::button or self::a or self::div][contains(translate(normalize-space(.),"
         " 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'zustimmen')]", By.XPATH),
        ("//*[self::button or self::a or self::div][contains(translate(normalize-space(.),"
         " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]", By.XPATH),
        ("//*[self::button or self::a or self::div][contains(translate(normalize-space(.),"
         " 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'alles akzeptieren')]", By.XPATH),
        ("//*[self::button or self::a or self::div][contains(translate(normalize-space(.),"
         " 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'ablehnen')]", By.XPATH),
        # „X“/Schließen
        ("button[aria-label*='close'],button[aria-label*='schließen'],[data-e2e*='close']", By.CSS_SELECTOR),
    ]
    for sel, how in candidates:
        try:
            els = driver.find_elements(how, sel) or []
            for el in els[:4]:
                if not el.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                try:
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)
                time.sleep(0.2)
        except Exception:
            pass


def ensure_comments_panel_open(driver, timeout: float = 6.0) -> bool:
    """
    Stellt sicher, dass der Kommentarbereich offen/sichtbar ist.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    s_list = "[data-e2e='comment-list'],[data-e2e='browse-comment-list'],[data-e2e='comment-scroll-list']"

    # Bereits sichtbar?
    try:
        if driver.find_elements(By.CSS_SELECTOR, s_list):
            return True
    except Exception:
        pass

    # Kommentar-Icon/Trigger finden
    triggers = [
        ("[data-e2e='comment-icon']", By.CSS_SELECTOR),
        ("//*[@role='button' or self::button][contains(translate(normalize-space(.),"
         " 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'kommentare')]", By.XPATH),
        ("//*[@role='button' or self::button][contains(translate(normalize-space(.),"
         " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'comments')]", By.XPATH),
    ]
    for sel, how in triggers:
        try:
            els = driver.find_elements(how, sel) or []
            for el in els[:2]:
                if not el.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                try:
                    WebDriverWait(driver, 2).until(EC.element_to_be_clickable(el))
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)
                break
        except Exception:
            pass

    # Warten bis Liste erscheint (best effort)
    try:
        WebDriverWait(driver, timeout).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, s_list)) > 0)
        return True
    except Exception:
        return False


def wait_for_initial_comments(driver, timeout: float = 12.0) -> bool:
    """
    Wartet, bis erste Kommentar-Container im DOM sind.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    sel = ("div[data-e2e='comment-item'],div[class*='DivCommentItemWrapper'],"
           "li[data-e2e*='comment'],div[class*='comment'][class*='item']")
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: (d.execute_script("return document.querySelectorAll(arguments[0]).length;", sel) or 0) > 0
        )
        return True
    except Exception:
        return False


def scroll_comments_area(driver, times: int = 3, pause: float = 0.25):
    """
    Scrollt in der Kommentar-Liste (falls vorhanden), sonst im Fenster.
    """
    from selenium.webdriver.common.by import By
    s_list = "[data-e2e='comment-list'],[data-e2e='browse-comment-list'],[data-e2e='comment-scroll-list']"
    try:
        lists = driver.find_elements(By.CSS_SELECTOR, s_list) or []
    except Exception:
        lists = []

    target = lists[0] if lists else None
    for _ in range(max(1, times)):
        try:
            if target:
                driver.execute_script("arguments[0].scrollTop += arguments[1];", target, 600)
            else:
                driver.execute_script("window.scrollBy(0, arguments[0]);", 600)
        except Exception:
            pass
        time.sleep(max(0.05, pause))


def sweep_virtualized_window(driver, sweeps: int = 6, step_ratio: float = 0.3, pause: float = 0.15):
    """
    Mehrfaches rauf/runter-Scrollen, um virtuelle Listen zu materialisieren.
    """
    try:
        h = driver.execute_script("return window.innerHeight || 900;")
    except Exception:
        h = 900
    step = max(120, int(h * max(0.1, min(0.8, step_ratio))))
    for _ in range(max(1, sweeps)):
        try:
            driver.execute_script("window.scrollBy(0, arguments[0]);", step)
            time.sleep(pause)
            driver.execute_script("window.scrollBy(0, arguments[0]);", -step // 2)
            time.sleep(pause)
        except Exception:
            pass


def hydrate_first_comments(driver, max_items: int = 150, pause: float = 0.06):
    """
    Scrollt die Top-Bereiche leicht an, um Lazy/IntersectionObserver zu triggern.
    """
    try:
        h = driver.execute_script("return window.innerHeight || 900;")
    except Exception:
        h = 900
    step = max(60, int(h * 0.2))
    total = 0
    while total < max_items:
        try:
            driver.execute_script("window.scrollBy(0, arguments[0]);", step)
            time.sleep(pause)
            driver.execute_script("window.scrollBy(0, arguments[0]);", -step)
            time.sleep(pause)
            total += 1
        except Exception:
            break