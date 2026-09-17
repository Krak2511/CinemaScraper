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
        print("[Warning] DISCORD_WEBHOOK_URL environment variable is NOT set.")
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
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if response.status_code in (200, 204):
            print("Successfully delivered Discord notification!")
        else:
            print(
                f"[Error] Discord API returned status {response.status_code}: {response.text}"
            )
    except Exception as e:
        print(f"[Error] Failed to execute Discord request: {e}")


def scrape_titles_from_page(page):
    """Extract titles currently loaded in the DOM."""
    titles = []
    elements = page.query_selector_all(
        "div.hover-mask div.line-clamp-6.text-ellipsis"
    )
    for el in elements:
        raw_title = el.inner_text().strip()
        if is_movie_title(raw_title):
            clean_title = raw_title.replace("Emperor Cinemas:", "").strip()
            formatted_title = f"Emperor Cinemas: {clean_title}"
            if formatted_title not in titles:
                titles.append(formatted_title)
    return titles


def fetch_live_movies():
    now_showing = []
    coming_soon = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector(".line-clamp-6", timeout=20000)

        # 1. Switch language to English if 'En' toggle is found
        try:
            en_btn = page.query_selector("div.cursor-pointer:has-text('En')")
            if en_btn:
                en_btn.click()
                page.wait_for_timeout(2000)
                page.wait_for_selector(".line-clamp-6", timeout=10000)
        except Exception as e:
            print(f"[Warning] Could not click language toggle: {e}")

        # 2. Extract 'Now Showing' titles from active tab
        now_showing = scrape_titles_from_page(page)

        # 3. Click 'Coming Soon' tab explicitly
        try:
            coming_soon_tab = page.query_selector("text=/Coming Soon|即將上映/")
            if coming_soon_tab:
                coming_soon_tab.click()
                page.wait_for_timeout(2000)
                coming_soon = scrape_titles_from_page(page)
        except Exception as e:
            print(f"[Warning] Could not switch to Coming Soon tab: {e}")

        browser.close()

    return {"coming_soon": coming_soon, "now_showing": now_showing}


if __name__ == "__main__":
    current_data = fetch_live_movies()
    seen_data = load_seen_movies()

    # Calculate differences against saved state
    new_now_showing = [
        m for m in current_data["now_showing"] if m not in seen_data["now_showing"]
    ]
    new_coming_soon = [
        m for m in current_data["coming_soon"] if m not in seen_data["coming_soon"]
    ]

    print(
        f"Scraped {len(current_data['now_showing'])} 'Now Showing' and {len(current_data['coming_soon'])} 'Coming Soon' titles."
    )

    if new_now_showing or new_coming_soon:
        print(
            f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' movies."
        )
        send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found since last run.")

    # Always update seen_movies.json with fresh state
    save_seen_movies(current_data)
    print("Updated seen_movies.json successfully.")
