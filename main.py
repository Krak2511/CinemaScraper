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


def fetch_live_movies():
    now_showing = []
    coming_soon = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded")

        # Wait for dynamic elements to render
        page.wait_for_selector(".line-clamp-6", timeout=20000)

        # Force English interface by clicking language switch icon if present
        try:
            lang_btn = page.query_selector("div.cursor-pointer:has-text('中')")
            if lang_btn:
                lang_btn.click()
                page.wait_for_timeout(2000)
        except Exception:
            pass

        # Scrape titles currently rendered in the active DOM tab
        title_elements = page.query_selector_all(
            "div.hover-mask div.line-clamp-6.text-ellipsis"
        )

        for el in title_elements:
            raw_title = el.inner_text().strip()

            if is_movie_title(raw_title):
                clean_title = raw_title.replace("Emperor Cinemas:", "").strip()
                formatted_title = f"Emperor Cinemas: {clean_title}"

                # Separate titles based on DOM section or fall back to default bucket
                is_coming_soon = el.evaluate(
                    """node => {
                    const textContent = document.body.innerText.lowerCase;
                    const section = node.closest('section, div[class*="content"]');
                    return section ? section.innerText.includes("Coming Soon") : false;
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

    # Determine differences
    new_now_showing = [
        m for m in current_data["now_showing"] if m not in seen_data["now_showing"]
    ]
    new_coming_soon = [
        m for m in current_data["coming_soon"] if m not in seen_data["coming_soon"]
    ]

    print(
        f"Scraped {len(current_data['now_showing'])} 'Now Showing' and {len(current_data['coming_soon'])} 'Coming Soon' movies."
    )

    if new_now_showing or new_coming_soon:
        print(
            f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' entries."
        )
        send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found since last check.")

    # Overwrite seen_movies.json with the freshly parsed structure
    save_seen_movies(current_data)
    print("Updated seen_movies.json successfully.")
