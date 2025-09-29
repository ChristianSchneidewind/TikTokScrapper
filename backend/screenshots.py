import os
import time
import re
from datetime import datetime, timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Basisordner für Screenshots; pro Video kommt ein Unterordner dazu
SCREEN_DIR_BASE = os.environ.get("SHOT_DIR", "geschossene_screenshots")
# Bestehende Dateien überschreiben? (Standard: nein)
OVERWRITE = os.environ.get("SHOT_OVERWRITE", "0") == "1"

# Kandidaten für Kommentar-Container
CONTAINER_SEL = (
    "div[data-e2e='comment-item'],"
    "div[class*='DivCommentItemWrapper'],"
    "li[data-e2e*='comment'],"
    "div[class*='comment'][class*='item']"
)


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def close_shortcut_overlay(driver, timeout=3):
    """
    Schließt das 'Tastenkombinationen'-Overlay:
    Findet den path des X im Container, ermittelt das umgebende <svg> und klickt es.
    """
    try:
        wait = WebDriverWait(driver, timeout)

        # 1) Warte optional auf den Shortcut-Container (wenn vorhanden)
        try:
            container = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class,'DivKeyboardShortcutContainer')]")
                )
            )
        except Exception:
            # Overlay evtl. (noch) nicht da – leise beenden
            return

        # 2) Finde das typische X-Path-Element (dein outerHTML beginnt mit M21.1718 23.9999…)
        #    -> dann den nächstliegenden <svg>-Vorfahren nehmen
        path_candidates = container.find_elements(
            By.XPATH,
            ".//*[name()='path' and starts-with(@d,'M21.1718 23.9999')]"
        )

        svg_to_click = None
        for p in path_candidates:
            try:
                svg = p.find_element(By.XPATH, "./ancestor::*[name()='svg'][1]")
                if svg.is_displayed():
                    svg_to_click = svg
                    break
            except Exception:
                continue

        # Fallback: irgendein sichtbares SVG im Container (falls d sich ändert)
        if not svg_to_click:
            svgs = container.find_elements(By.XPATH, ".//*[name()='svg']")
            for s in svgs:
                try:
                    if s.is_displayed():
                        svg_to_click = s
                        break
                except Exception:
                    continue

        if not svg_to_click:
            # Letzter Fallback: ESC schließt häufig das Overlay
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                print("✅ Overlay schließen via ESC (Fallback).")
            except Exception:
                pass
            return

        # 3) Mehrstufig klicken
        try:
            svg_to_click.click()
            print("✅ Overlay geschlossen (direct click auf <svg>).")
            time.sleep(0.2)
            return
        except Exception:
            pass

        try:
            ActionChains(driver).move_to_element(svg_to_click).click().perform()
            print("✅ Overlay geschlossen (ActionChains).")
            time.sleep(0.2)
            return
        except Exception:
            pass

        try:
            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}))",
                svg_to_click
            )
            print("✅ Overlay geschlossen (JS-Dispatch).")
            time.sleep(0.2)
            return
        except Exception:
            pass

        # 4) ESC als letzter Versuch
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            print("✅ Overlay geschlossen (ESC).")
        except Exception:
            print("⚠️ Overlay-❌ nicht klickbar – bitte erneut prüfen.")

    except Exception as e:
        print(f"ℹ️ close_shortcut_overlay: {e}")






def _now_datetime():
    return datetime.now(timezone.utc)

def _now_date_yyyymmdd():
    return datetime.now().strftime("%Y-%m-%d")  # yyyy-mm-dd


def _norm_text(s: str | None, maxlen=80):
    if not s:
        return ""
    t = re.sub(r"\s+", " ", s).strip()
    if len(t) > maxlen:
        t = t[:maxlen].rstrip() + "…"
    return t

def _safe_part(s: str) -> str:
    """Für Ordner-/Dateinamen zulässige Zeichen erzwingen."""
    return re.sub(r"[^a-zA-Z0-9._:-]", "_", str(s or ""))

def _get_bounding_rect(driver, el):
    return driver.execute_script("""
        const r = arguments[0].getBoundingClientRect();
        return {top:r.top, left:r.left, width:r.width, height:r.height, bottom:r.bottom, right:r.right};
    """, el)

def _scroll_into_center(rect, driver):
    """Fenster so scrollen, dass das Element ungefähr mittig steht."""
    driver.execute_script("""
        const r = arguments[0];
        const W = window;
        const y = Math.max(0, r.top + W.pageYOffset - (W.innerHeight/2 - r.height/2));
        W.scrollTo({top: y, behavior: "instant"});
    """, rect)

def _highlight_and_url_banner(driver, el, url_text: str):
    """
    Kommentar rot umranden + URL als feste Leiste unten einblenden.
    Gibt (className, bannerId) zurück, um danach aufzuräumen.
    """
    class_name = f"__shot_sel_{int(time.time()*1000)}"
    banner_id = f"__shot_url_{int(time.time()*1000)}"

    driver.execute_script("""
        const el = arguments[0];
        const className = arguments[1];
        const bannerId = arguments[2];
        const urlText = arguments[3];

        // rote Outline
        el.classList.add(className);
        let style = document.getElementById("__shot_style");
        if (!style) {
            style = document.createElement("style");
            style.id = "__shot_style";
            document.head.appendChild(style);
        }
        style.textContent += `
            .${className} {
                outline: 3px solid red !important;
                outline-offset: 2px !important;
                border-radius: 6px !important;
            }
        `;

        // URL-Banner unten mit UTC-Zeitstempel
        let banner = document.getElementById(bannerId);
        if (!banner) {
            const timestamp = new Date().toISOString().replace(/\\.\\d{3}Z$/, "Z");

            banner = document.createElement("div");
            banner.id = bannerId;
            banner.innerHTML = `
                <div style="font-weight:bold;">${urlText || ""}</div>
                <div style="opacity:0.8;">${timestamp}</div>
            `;
            Object.assign(banner.style, {
                position: "fixed",
                left: "0",
                right: "0",
                bottom: "0",
                padding: "6px 10px",
                fontFamily: "monospace, system-ui, sans-serif",
                fontSize: "11px",
                color: "#fff",
                background: "rgba(0,0,0,0.75)",
                zIndex: "2147483647",
                textAlign: "left",
                pointerEvents: "none",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: "100vw"
            });
            document.body.appendChild(banner);
        }
        return [className, bannerId];
    """, el, class_name, banner_id, url_text)

    return class_name, banner_id


    return class_name, banner_id

def _cleanup_highlight_and_banner(driver, el, class_name, banner_id):
    driver.execute_script("""
        const el = arguments[0];
        const className = arguments[1];
        const bannerId = arguments[2];
        if (el) { try { el.classList.remove(className); } catch(e){} }
        const banner = document.getElementById(bannerId);
        if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
    """, el, class_name, banner_id)

def _find_comment_element_by_cid(driver, cid: str):
    """Suche Container anhand möglicher CID-Attribute/Links."""
    if not cid:
        return None
    selectors = [
        f"[data-cid='{cid}']",
        f"[data-comment-id='{cid}']",
        f"[data-e2e-cid='{cid}']",
        f"[data-id='{cid}']",
        f"a[href*='cid={cid}']",
        f"a[href*='/comment/{cid}']",
    ]
    for sel in selectors:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for e in els:
                container = driver.execute_script(
                    "return arguments[0].closest(arguments[1]) || arguments[0];",
                    e, CONTAINER_SEL
                )
                if container:
                    return container
        except Exception:
            continue
    return None

def _xpath_literal(s: str) -> str:
    """Sichere Einbettung eines Strings in XPath (mit ' und ")."""
    if '"' not in s:
        return f'"{s}"'
    if "'" not in s:
        return f"'{s}'"
    parts = s.split('"')
    # concat("foo","\"", "bar", "\"", "baz")
    out = []
    for i, p in enumerate(parts):
        if p:
            out.append(f'"{p}"')
        if i < len(parts) - 1:
            out.append("'\"'")
    return "concat(" + ", ".join(out) + ")"

def _find_comment_element_fuzzy(driver, row):
    """Fallback: per Text-Snippet geeigneten Container finden (reines XPath)."""
    text = (row.get("text") or "").strip()
    snippet = _norm_text(text, maxlen=40)
    if not snippet:
        snippet = (str(row.get("cid") or "") or "")[:12]

    lit = _xpath_literal(snippet)
    arms = [
        f"//div[@data-e2e='comment-item']",
        f"//div[contains(@class,'DivCommentItemWrapper')]",
        f"//li[contains(@data-e2e,'comment')]",
        f"//div[contains(@class,'comment')][contains(@class,'item')]",
    ]
    arms = [f"{a}[.//text()[contains(normalize-space(.), {lit})]]" for a in arms]
    xp = " | ".join(arms)

    try:
        candidates = driver.find_elements(By.XPATH, xp)
    except Exception:
        candidates = []

    return candidates[0] if candidates else None

def _refind_comment_with_retry(driver, row, tries=3, pause=0.18):
    """Mehrfach versuchen (inkl. Minisweep), um virtualisierte Knoten zu materialisieren."""
    for _ in range(tries):
        el = _find_comment_element_by_cid(driver, str(row.get("cid") or ""))
        if not el:
            el = _find_comment_element_fuzzy(driver, row)
        if el:
            return el
        # Mini-Sweep: leicht rauf/runter scrollen
        try:
            h = driver.execute_script("return window.innerHeight || 800;")
        except Exception:
            h = 800
        step = max(100, int(h * 0.28))
        driver.execute_script("window.scrollBy(0, arguments[0]);", step)
        time.sleep(pause)
        driver.execute_script("window.scrollBy(0, arguments[0]);", -step//2)
        time.sleep(pause)
    return None

def screenshot_comments_and_replies(driver, video_id: str, rows: list[dict]):
    """
    Erzeugt Viewport-Screenshots für Kommentare:
    - Unterordner pro Video-ID: geschossene_screenshots/<videoid>/
    - Dateiname: DD-MM-YYYY_<cid>.png
    - Kommentar mittig, rot umrandet, URL-Banner unten
    - pro Kommentar höchstens ein Bild pro Tag (Skip, außer OVERWRITE)
    """
    # Zielordner pro Video
    video_folder = os.path.join(SCREEN_DIR_BASE, _safe_part(video_id))
    _ensure_dir(video_folder)


    # Gesehene Kommentare (CID/Key) – pro Run keine Duplikate
    seen = set()
    date_prefix = _now_date_yyyymmdd()

    # Seite-URL für Banner
    try:
        url_text = driver.execute_script("return location.href;") or ""
    except Exception:
        url_text = ""

    # Shortcut-Overlay (Tastenkombinationen) schließen, falls vorhanden
    close_shortcut_overlay(driver)

    for row in rows:
        # Eindeutiger Schlüssel bevorzugt echte CID
        cid = str(row.get("cid") or "")
        if not cid or cid.startswith("dom_"):
            user = (row.get("user") or "").strip().lower()
            ts = int(row.get("timestamp") or 0)
            text_key = _norm_text(row.get("text") or "", maxlen=80).lower()
            key = f"key:{user}|{ts}|{text_key}"
        else:
            key = cid

        if key in seen:
            continue

        # Element suchen (mit Retry & Minisweep)
        el = _refind_comment_with_retry(driver, row, tries=3, pause=0.18)
        if not el:
            print(f"⚠️  Container nicht gefunden (cid={cid}). Übersprungen.")
            continue

        rect = _get_bounding_rect(driver, el)
        if rect:
            _scroll_into_center(rect, driver)
            time.sleep(0.12)

        # Highlight + URL-Banner einblenden
        try:
            class_name, banner_id = _highlight_and_url_banner(driver, el, url_text)
        except Exception:
            class_name, banner_id = None, None

        # Dateiname ohne laufende Nummer; Duplikate am selben Tag verhindern
        safe_cid = _safe_part(cid or key)
        filename = f"{date_prefix}_{safe_cid}.png"
        out_path = os.path.join(video_folder, filename)

        if os.path.exists(out_path) and not OVERWRITE:
            print(f"⏭️  Schon vorhanden, übersprungen: {os.path.join(_safe_part(video_id), filename)}")
            seen.add(key)
            try:
                _cleanup_highlight_and_banner(driver, el, class_name, banner_id)
            except Exception:
                pass
            continue

        ok = driver.save_screenshot(out_path)
        if ok:
            seen.add(key)
            action = "überschrieben" if OVERWRITE else "gespeichert"
            print(f"✅ Viewport-Screenshot {action}: {os.path.join(_safe_part(video_id), filename)}")
        else:
            print(f"❌ Screenshot fehlgeschlagen: {os.path.join(_safe_part(video_id), filename)}")

        # Cleanup
        try:
            _cleanup_highlight_and_banner(driver, el, class_name, banner_id)
        except Exception:
            pass