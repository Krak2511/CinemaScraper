import json
import os
import re
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SEEN_MOVIES_FILE = "seen_movies.json"

PROMO_KEYWORDS = [
    r"macau\d+",
    r"mop\s*\d+",
    r"promo",
    r"yummy box",
    r"special offer",
    r"popcorn",
]


def is_movie_title(text):
    if not text:
        return False
    clean_text = text.replace("Emperor Cinemas:", "").strip()
    for pattern in PROMO_KEYWORDS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False
    return len(clean_text) > 0


def load_seen_movies():
    if os.path.exists(SEEN_MOVIES_FILE):
        try:
            with open(SEEN_MOVIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"now_showing": [], "coming_soon": []}


def save_seen_movies(seen_data):
    with open(SEEN_MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_data, f, indent=2, ensure_ascii=False)


def send_discord_notification(new_now_showing, new_coming_soon):
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL is not configured. Skipping notification.")
        return

    fields = []
    if new_now_showing:
        fields.append(
            {
                "name": "🎬 New Now Showing",
                "value": "\n".join([f"• {title}" for title in new_now_showing]),
            }
        )

    if new_coming_soon:
        fields.append(
            {
                "name": "⏳ New Coming Soon",
                "value": "\n".join([f"• {title}" for title in new_coming_soon]),
            }
        )

    if not fields:
        return

    payload = {
        "embeds": [
            {
                "title": "🎭 New Movies Detected on Emperor Cinemas!",
                "color": 3447003,
                "fields": fields,
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        print("Successfully sent Discord notification.")
    except Exception as e:
        print(f"Failed to send Discord webhook: {e}")


def fetch_live_movies():
    now_showing = []
    coming_soon = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector(".line-clamp-6", timeout=20000)

        title_elements = page.query_selector_all(
            "div.hover-mask div.line-clamp-6.text-ellipsis"
        )

        for el in title_elements:
            raw_title = el.inner_text().strip()

            if is_movie_title(raw_title):
                clean_title = raw_title.replace("Emperor Cinemas:", "").strip()
                formatted_title = f"Emperor Cinemas: {clean_title}"

                is_coming_soon = el.evaluate(
                    """node => {
                    const parent = node.closest('[class*="soon"], [id*="soon"]');
                    return parent !== null;
                }"""
                )

                if is_coming_soon:
                    if formatted_title not in coming_soon:
                        coming_soon.append(formatted_title)
                else:
                    if formatted_title not in now_showing:
                        now_showing.append(formatted_title)

        browser.close()

    return {"coming_soon": coming_soon, "now_showing": now_showing}


if __name__ == "__main__":
    current_data = fetch_live_movies()
    seen_data = load_seen_movies()

    # Identify newly discovered movies
    new_now_showing = [
        m for m in current_data["now_showing"] if m not in seen_data["now_showing"]
    ]
    new_coming_soon = [
        m for m in current_data["coming_soon"] if m not in seen_data["coming_soon"]
    ]

    # Notify if there are new titles
    if new_now_showing or new_coming_soon:
        print(
            f"Found {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' movies."
        )
        send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found.")

    # Update state file
    save_seen_movies(current_data)
    print(json.dumps(current_data, indent=2, ensure_ascii=False))
