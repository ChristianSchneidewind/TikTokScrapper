# backend/browser.py
import os, re, subprocess
import undetected_chromedriver as uc
from .config import logger
from selenium.webdriver.support import expected_conditions as EC

def _detect_chrome_binary_candidates():
    env_bin = os.getenv("CHROME_BINARY")
    return [
        env_bin,
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    ]

def _get_chrome_version_major(binary_path: str):
    try:
        out = subprocess.check_output([binary_path, "--version"], stderr=subprocess.STDOUT, text=True, timeout=5)
        m = re.search(r"(\d+)\.\d+\.\d+\.\d+", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None

def launch_browser():
    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    version_main = None
    for path in _detect_chrome_binary_candidates():
        if path and os.path.exists(path):
            opts.binary_location = path
            vm = _get_chrome_version_major(path)
            if vm:
                version_main = vm
                break

    env_bin = os.getenv("CHROME_BINARY")
    if env_bin and os.path.exists(env_bin):
        opts.binary_location = env_bin
        vm = _get_chrome_version_major(env_bin)
        if vm:
            version_main = vm

    driver = uc.Chrome(options=opts, version_main=version_main) if version_main else uc.Chrome(options=opts)

    # Fenstergröße (Viewport-Screenshots nutzen diese Größe)
    driver.set_window_rect(width=768, height=1024)

    # Request-Manipulation (count=100 für comment/list)
    override_js = """
        (function(open){XMLHttpRequest.prototype.open=function(m,u){
            if(u && u.includes('/api/comment/list/')) {
                const s = u.includes('?') ? '&' : '?';
                u = u + s + 'count=100';
            }
            return open.call(this, m, u);
        }})(XMLHttpRequest.prototype.open);
        (function(orig){
            window.fetch = function(resource, init) {
                let u = typeof resource === 'string' ? resource : (resource && resource.url);
                if(u && u.includes('/api/comment/list/')) {
                    const U = new URL(u, window.location.origin);
                    U.searchParams.set('count', '100');
                    resource = U.toString();
                }
                return orig.call(this, resource, init);
            };
        })(window.fetch);
    """
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": override_js})
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Accept-Language": "de-DE,de;q=0.9,en-US,en;q=0.8"}})

    try:
        driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["*.mp4", "*.m3u8", "*.webm"]})
    except Exception:
        pass

    return driver