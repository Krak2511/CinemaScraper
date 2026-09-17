import json
import os
import requests
from playwright.sync_api import sync_playwright

# Configuration
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
SEEN_MOVIES_FILE = "seen_movies.json"


def load_seen_movies():
    if os.path.exists(SEEN_MOVIES_FILE):
        try:
            with open(SEEN_MOVIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {SEEN_MOVIES_FILE}: {e}")
    return {"now_showing": [], "coming_soon": []}


def save_seen_movies(seen_data):
    try:
        with open(SEEN_MOVIES_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_data, f, ensure_ascii=False, indent=2)
        print("Updated seen_movies.json successfully.")
    except Exception as e:
        print(f"Error saving {SEEN_MOVIES_FILE}: {e}")


# --- SCRAPERS ---


def scrape_mcl(page):
    now_showing = set()
    coming_soon = set()

    # Scraping MCL Now Showing
    try:
        page.goto("https://www.mclcinema.com/Index.aspx", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".movie-title, .film-name", timeout=15000)
        titles = page.locator(".movie-title, .film-name").all_text_contents()
        now_showing.update([t.strip() for t in titles if t.strip()])
    except Exception as e:
        print(f"Error scraping MCL Now Showing: {e}")

    # Scraping MCL Coming Soon
    try:
        page.goto("https://www.mclcinema.com/ComingSoon.aspx", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".movie-title, .film-name", timeout=15000)
        titles = page.locator(".movie-title, .film-name").all_text_contents()
        coming_soon.update([t.strip() for t in titles if t.strip()])
    except Exception as e:
        print(f"Error scraping MCL Coming Soon: {e}")

    return now_showing, coming_soon


def scrape_broadway(page):
    now_showing = set()
    coming_soon = set()

    # Scraping Broadway Now Showing
    try:
        page.goto("https://www.cinema.com.hk/tc/movie", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".movie-name, .film-title", timeout=15000)
        titles = page.locator(".movie-name, .film-title").all_text_contents()
        now_showing.update([t.strip() for t in titles if t.strip()])
    except Exception as e:
        print(f"Error scraping Broadway Now Showing: {e}")

    # Scraping Broadway Coming Soon
    try:
        page.goto("https://www.cinema.com.hk/tc/movie/coming-soon", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".movie-name, .film-title", timeout=15000)
        titles = page.locator(".movie-name, .film-title").all_text_contents()
        coming_soon.update([t.strip() for t in titles if t.strip()])
    except Exception as e:
        print(f"Error scraping Broadway Coming Soon: {e}")

    return now_showing, coming_soon


def scrape_emperor(page):
    now_showing = set()
    coming_soon = set()

    url = "https://www.emperocinemas.com/zh"  # adjust URL if needed
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # 1. Scrape Now Showing
        page.wait_for_selector("div[data-text='NOW SHOWING'], button:has-text('NOW SHOWING')", timeout=15000)
        titles = page.locator(".stable-bold, .movie-title, h3, h4").all_text_contents()
        for t in titles:
            text = t.strip()
            if text and text not in ["NOW SHOWING", "COMING SOON", "SPECIAL PROGRAM", "BY MOVIE", "BY TIME"]:
                now_showing.add(text)

        # 2. Switch tab to Coming Soon via tab button
        coming_soon_btn = page.locator("button:has(div[data-text='COMING SOON']), button:has-text('COMING SOON')").first
        if coming_soon_btn.is_visible():
            coming_soon_btn.click()
            page.wait_for_timeout(2000)

            # Scrape Coming Soon titles
            titles_cs = page.locator(".stable-bold, .movie-title, h3, h4").all_text_contents()
            for t in titles_cs:
                text = t.strip()
                if text and text not in ["NOW SHOWING", "COMING SOON", "SPECIAL PROGRAM", "BY MOVIE", "BY TIME"]:
                    coming_soon.add(text)

    except Exception as e:
        print(f"Error scraping Emperor Cinemas: {e}")

    return now_showing, coming_soon


# --- DISCORD NOTIFICATION WITH CHUNKING ---


def send_discord_notification(new_now_showing, new_coming_soon):
    if not DISCORD_WEBHOOK_URL:
        print("No Discord Webhook URL provided. Skipping notification.")
        return

    fields = []
    if new_now_showing:
        fields.append(("🎬 New 'Now Showing' Movies", new_now_showing))
    if new_coming_soon:
        fields.append(("📅 New 'Coming Soon' Movies", new_coming_soon))

    if not fields:
        return

    # Helper function to send an embed payload
    def send_embed_batch(embed_fields):
        payload = {
            "username": "Movie Notifier",
            "embeds": [
                {
                    "title": "🎞️ Movie Cinema Updates",
                    "color": 3447003,
                    "fields": embed_fields,
                }
            ],
        }
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if resp.status_code not in (200, 204):
            print(f"[Error] Discord API status {resp.status_code}: {resp.text}")
        else:
            print("Discord notification sent successfully.")

    # Process and split large updates to strictly observe Discord's 6,000 character limit
    current_batch_fields = []
    current_char_count = 50  # account for title character weight

    for title, movies in fields:
        # Group titles in chunks to guarantee single fields stay under 1024 chars
        chunk = []
        chunk_len = 0

        for movie in movies:
            item_str = f"• {movie}\n"
            if chunk_len + len(item_str) > 1000:
                field_val = "".join(chunk)
                if current_char_count + len(field_val) + len(title) > 5500:
                    send_embed_batch(current_batch_fields)
                    current_batch_fields = []
                    current_char_count = 50

                current_batch_fields.append({"name": title, "value": field_val, "inline": False})
                current_char_count += len(title) + len(field_val)
                chunk = [item_str]
                chunk_len = len(item_str)
            else:
                chunk.append(item_str)
                chunk_len += len(item_str)

        if chunk:
            field_val = "".join(chunk)
            if current_char_count + len(field_val) + len(title) > 5500:
                send_embed_batch(current_batch_fields)
                current_batch_fields = []
                current_char_count = 50

            current_batch_fields.append({"name": title, "value": field_val, "inline": False})
            current_char_count += len(title) + len(field_val)

    if current_batch_fields:
        send_embed_batch(current_batch_fields)


# --- MAIN EXECUTION ---


def main():
    seen_data = load_seen_movies()
    seen_now_showing = set(seen_data.get("now_showing", []))
    seen_coming_soon = set(seen_data.get("coming_soon", []))

    all_now_showing = set()
    all_coming_soon = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Scrape MCL
        mcl_ns, mcl_cs = scrape_mcl(page)
        all_now_showing.update(mcl_ns)
        all_coming_soon.update(mcl_cs)

        # Scrape Broadway
        bway_ns, bway_cs = scrape_broadway(page)
        all_now_showing.update(bway_ns)
        all_coming_soon.update(bway_cs)

        # Scrape Emperor
        emp_ns, emp_cs = scrape_emperor(page)
        all_now_showing.update(emp_ns)
        all_coming_soon.update(emp_cs)

        browser.close()

    print(f"Scraped {len(all_now_showing)} 'Now Showing' and {len(all_coming_soon)} 'Coming Soon' titles.")

    # Determine new entries
    new_now_showing = sorted(list(all_now_showing - seen_now_showing))
    new_coming_soon = sorted(list(all_coming_soon - seen_coming_soon))

    print(f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' entries.")

    # Send notifications in chunks
    if new_now_showing or new_coming_soon:
        send_discord_notification(new_now_showing, new_coming_soon)

    # Save state
    save_seen_movies(
        {
            "now_showing": sorted(list(all_now_showing | seen_now_showing)),
            "coming_soon": sorted(list(all_coming_soon | seen_coming_soon)),
        }
    )


if __name__ == "__main__":
    main()
