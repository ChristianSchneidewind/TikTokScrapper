# backend/selectors.py
from selenium.webdriver.common.by import By

SEL = {
    # Kommentar-Container
    "comment_containers": (
        By.CSS_SELECTOR,
        "div[data-e2e='comment-item'],"
        "div[class*='DivCommentItemWrapper'],"
        "li[data-e2e*='comment'],"
        "div[class*='comment'][class*='item']"
    ),

    # Reply-Container
    "reply_containers": (
        By.CSS_SELECTOR,
        "div[data-e2e='comment-reply-item'],"
        "li[data-e2e*='reply'],"
        "div[class*='reply'][class*='item']"
    ),

    # Usernamen
    "username": (
        By.CSS_SELECTOR,
        "[data-e2e='comment-username'],"
        "[data-e2e='comment-user-uniqueid']"
    ),

    # Kommentar-Text
    "comment_text": (
        By.CSS_SELECTOR,
        "[data-e2e='comment-text'],"
        "[data-e2e='reply-text']"
    ),

    # Replies expandieren (Antworten anzeigen / Mehr anzeigen)
    "reply_expand": (
        By.XPATH,
        "//*[(self::button or self::span or self::a) and not(@disabled)"
        " and not(ancestor::div[contains(@class,'editor')])"
        " and ("
        "   contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), 'view replies')"
        "   or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), 'antwort')"
        "   or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), 'weitere antworten')"
        "   or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), 'replies')"
        "   or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), 'mehr anzeigen')"
        " )]"
    ),
}