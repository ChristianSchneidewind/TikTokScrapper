# backend/auth.py
import json, os, time
from urllib import request, parse
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from .config import COOKIE_FILE, TIKTOK_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger

def _has_session(driver):
    try:
        return any(c.get("name") == "sessionid" for c in driver.get_cookies())
    except Exception:
        return False

def _notify_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram nicht konfiguriert (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID fehlen).")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
    try:
        req = request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        request.urlopen(req, timeout=10).read()
    except Exception as e:
        logger.warning(f"Telegram-Notify fehlgeschlagen: {e}")

def _wait_for_manual_login_and_save(driver, timeout_sec=300):
    logger.info(f"Bitte jetzt manuell einloggen – Wartefenster {timeout_sec}s.")
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        if _has_session(driver):
            os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
            json.dump(driver.get_cookies(), open(COOKIE_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            try:
                os.chmod(COOKIE_FILE, 0o600)
            except Exception:
                pass
            _notify_telegram("✅ TikTok: Login erkannt – Cookies aktualisiert.")
            logger.info("Login erkannt – Cookies gespeichert.")
            return True
        time.sleep(2)
    return False

def ensure_logged_in(driver):
    driver.get(TIKTOK_URL)

    if os.path.exists(COOKIE_FILE):
        try:
            cookies = json.load(open(COOKIE_FILE, encoding="utf-8"))
        except Exception:
            cookies = []
        for c in cookies:
            try:
                if ".tiktok.com" not in c.get("domain", ""):
                    continue
                ck = {k: c.get(k) for k in ("name", "value", "domain", "path", "secure") if c.get(k) is not None}
                if c.get("expiry") is not None:
                    ck["expiry"] = int(c["expiry"])
                driver.add_cookie(ck)
            except Exception:
                continue
        driver.refresh()

    try:
        WebDriverWait(driver, 30).until(lambda d: _has_session(d))
    except TimeoutException:
        logger.error("Login nicht vorhanden / Cookies abgelaufen.")
        _notify_telegram("⚠️ TikTok: Cookies abgelaufen – manuelle Anmeldung erforderlich.")
        driver.get(TIKTOK_URL)
        if not _wait_for_manual_login_and_save(driver, timeout_sec=300):
            logger.error("Manueller Login nicht erfolgt – Abbruch.")
            _notify_telegram("❌ TikTok: Manuelle Anmeldung nicht erfolgt – Prozess abgebrochen.")
            return False

    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
    json.dump(driver.get_cookies(), open(COOKIE_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    try:
        os.chmod(COOKIE_FILE, 0o600)
    except Exception:
        pass
    return True