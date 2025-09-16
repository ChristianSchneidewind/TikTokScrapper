# 📥 TikTokScrapper

Ein automatisierter TikTok-Kommentar-Scraper mit **sichtbarem Playwright-Browser**, **Stealth-Modus**, Cookie-Handling und Region-Switching für 🇩🇪 DE & 🇺🇸 US.

---

## 🔧 Features

- 🖥 **Nicht-headless** für maximale TikTok-Kompatibilität
- 🌍 Unterstützt **mehrere Regionen** (DE und US)
- 🕵️‍♂️ Stealth-Mode gegen Bot-Erkennung
- 🍪 Cookie-Reuse für Login-Freiheit
- Telegram-Benachrichtigung bei abgelaufenen Cookies
- 🧠 Kommentar-Scraping inkl. Username, Timestamp und Comment-ID
- 🖼 Automatische Screenshot-Funktion (einmal pro Kommentar-ID)
- 💬 Unterstützung für Parent- und Reply-Kommentare
- 🧩 Merge-Logik für DE + US nach Kommentar-ID


🛡 Haftungsausschluss

Dieses Projekt dient ausschließlich zu Bildungszwecken. Das Scrapen von Inhalten kann gegen die Nutzungsbedingungen von TikTok verstoßen. Verwende dieses Tool verantwortungsvoll und auf eigenes Risiko

📲 Telegram-Bot einrichten

Um Benachrichtigungen über den Scraper per Telegram zu erhalten, brauchst du einen eigenen Bot:

Öffne in Telegram den Chat mit @BotFather

Sende den Befehl /newbot

Vergib einen Namen und einen eindeutigen Benutzernamen (endet auf _bot, z. B. TikTokScraper_bot).

BotFather gibt dir anschließend einen API-Token (z. B. 123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11).
👉 Diesen Token speicherst du dir sicher ab, er wird später im Skript benötigt

🆔 Eigene Chat-ID herausfinden

Damit der Bot weiß, wohin er Nachrichten schicken soll, musst du deine Chat-ID herausfinden:

Starte den Bot in Telegram, indem du ihm /start sendest.
Führe im Projekt das Hilfsskript aus:

python test_telegram.py

Das Skript gibt dir deine Chat-ID in der Konsole aus.
Diese ID trägst du später in deine .env Datei ein.