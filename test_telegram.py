# backend/test_telegram.py
import os
import sys
import time
import argparse
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("Bitte installieren: pip install python-dotenv requests")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv()  # fallback

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("Fehlt: TELEGRAM_BOT_TOKEN in .env")
    sys.exit(1)

API = f"https://api.telegram.org/bot{TOKEN}"

def api_get(method, **params):
    r = requests.get(f"{API}/{method}", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API-Fehler: {data}")
    return data["result"]

def api_post(method, **json_payload):
    r = requests.post(f"{API}/{method}", json=json_payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API-Fehler: {data}")
    return data["result"]

def delete_webhook():
    try:
        api_get("deleteWebhook", drop_pending_updates=True)
    except Exception as e:
        print(f"Warnung: deleteWebhook fehlgeschlagen: {e}")

def whoami():
    me = api_get("getMe")
    print(f"Bot ok ✅  username=@{me.get('username')}  id={me.get('id')}")
    return me

def send_test(chat_id, text="✅ Test: Bot funktioniert!"):
    try:
        api_post("sendMessage", chat_id=chat_id, text=text, disable_notification=True)
        print(f"Testnachricht gesendet an CHAT_ID={chat_id}")
    except Exception as e:
        print(f"Fehler beim Senden: {e}")

def find_chats(max_rounds=6, poll_timeout=5):
    """
    Sammelt Chats aus Updates:
    - Nachrichten (message/edited_message/channel_post)
    - Mitgliedschafts-Events (my_chat_member/chat_member), damit Gruppen auch ohne Erwähnung erkannt werden.
    """
    found = {}
    last_update_id = None
    for _ in range(max_rounds):
        try:
            result = api_get(
                "getUpdates",
                offset=(last_update_id + 1) if last_update_id else None,
                timeout=poll_timeout,
                allowed_updates=["message","edited_message","channel_post","my_chat_member","chat_member"],
            )
        except requests.exceptions.ReadTimeout:
            result = []
        except Exception as e:
            print(f"getUpdates-Fehler: {e}")
            result = []

        for upd in result:
            last_update_id = upd.get("update_id", last_update_id)
            # Nachrichten
            msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
            if msg and "chat" in msg:
                chat = msg["chat"]
                found[chat["id"]] = (chat.get("type"), chat.get("title") or chat.get("username") or "(ohne Titel)")
            # Mitgliedschafts-Events
            for key in ("my_chat_member", "chat_member"):
                cm = upd.get(key)
                if cm and "chat" in cm:
                    chat = cm["chat"]
                    found[chat["id"]] = (chat.get("type"), chat.get("title") or chat.get("username") or "(ohne Titel)")

        if found:
            break
        time.sleep(1)

    return found

def main():
    parser = argparse.ArgumentParser(description="Finde Telegram Chat-ID(s) und teste den Bot.")
    parser.add_argument("--whoami", action="store_true", help="Prüfe Bot-Token via getMe.")
    parser.add_argument("--send", metavar="CHAT_ID", help="Sende Testnachricht an diese Chat-ID.")
    args = parser.parse_args()

    delete_webhook()  # Safety: sicherstellen, dass getUpdates funktioniert

    if args.whoami:
        whoami()

    if args.send:
        send_test(args.send)
        return

    print("Tipp:")
    print("  1) Füge den Bot zur gewünschten Gruppe hinzu.")
    print("  2) Schreibe in der Gruppe eine Nachricht, ODER erwähne den Bot (@DeinBot),")
    print("     ODER deaktiviere Privacy bei @BotFather (/setprivacy -> Disable).")
    print("  3) Dann dieses Script erneut ausführen (es pollt kurz).")

    me = whoami()

    print("\nSuche nach Chats (bis ~30 Sekunden)…")
    chats = find_chats(max_rounds=6, poll_timeout=5)

    if not chats:
        print("\nKeine Chats gefunden.")
        print("Checkliste:")
        print(" - Bot ist Mitglied der Gruppe?")
        print(" - In der Gruppe eine Nachricht gesendet (oder Bot erwähnt)?")
        print(" - Privacy-Mode ggf. bei @BotFather mit /setprivacy -> Disable")
        print(" - Kein Webhook aktiv (dieses Skript löscht ihn zu Beginn)")
        sys.exit(2)

    print("\nGefundene Chats (verwende die ID deiner Gruppe):")
    for cid, (ctype, title) in chats.items():
        print(f" - Chat-ID: {cid}    Typ: {ctype}    Titel/Name: {title}")

    # Optional: Wenn TELEGRAM_CHAT_ID bereits in .env steht, Test senden
    env_chat = os.getenv("TELEGRAM_CHAT_ID")
    if env_chat:
        print(f"\nTeste TELEGRAM_CHAT_ID aus .env: {env_chat}")
        send_test(env_chat, "✅ Test aus test_telegram.py (.env)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
