# backend/utils.py
import hashlib
import re
import unicodedata
from selenium.webdriver.support.ui import WebDriverWait

def safe_int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default

def _norm_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def _norm_user(u: str | None) -> str:
    if not u:
        return ""
    u = unicodedata.normalize("NFKC", str(u)).strip()
    if u.startswith("@"):
        u = u[1:]
    return u.lower()

def count_dom_cids(items):
    return sum(1 for d in items if isinstance(d, dict) and str(d.get("cid") or "").startswith("dom_"))

def wait_for_nonzero_height(driver, el, timeout=5):
    WebDriverWait(driver, timeout).until(lambda d: el.size and el.rect["height"] > 0)

def sha1_16(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]