# backend/runner.py
import os, re
from .config import logger, URLS_FILE
from .browser import launch_browser
from .auth import ensure_logged_in
from .scrape import scrape_comments


def run():
    driver = launch_browser()
    try:
        if not ensure_logged_in(driver):
            return

        if not os.path.exists(URLS_FILE):
            logger.error(f"{URLS_FILE} fehlt.")
            return

        # URLs einlesen und Kommentare/Leere Zeilen überspringen
        urls = []
        with open(URLS_FILE, encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#") or line.startswith("//"):
                    logger.info(f"⏭️  Überspringe kommentierte Zeile: {line}")
                    continue
                urls.append(line)

        if not urls:
            logger.warning("⚠️ Keine gültigen URLs in video_urls.txt gefunden.")
            return

        # Iteration über alle gültigen URLs
        for url in urls:
            if not re.search(r"/video/\d+", url):
                logger.warning(f"Ungültige URL: {url}")
                continue

            vid = re.search(r"/video/(\d+)", url).group(1)
            logger.info(f"🌐 Scraping Kommentare & Screenshots für Video {vid}")
            out = os.path.join(os.path.dirname(URLS_FILE), f"comments_{vid}.json")

            try:
                scrape_comments(driver, url, out, scroll_pause=0.8, take_screenshots=True)
            except Exception as e:
                logger.exception(f"❌ Fehler beim Verarbeiten von {url}: {e}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass