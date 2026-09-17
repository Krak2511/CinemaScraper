import json
import os
import re
import requests
from playwright.sync_api import sync_playwright

# URLs
EMPEROR_URL = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS&lang=en-US"
MCL_NOW_SHOWING_URL = "https://www.mclcinema.com/NowShowing.aspx?visLang=2"
MCL_COMING_SOON_URL = "https://www.mclcinema.com/ComingSoon.aspx?visLang=2"
BROADWAY_NOW_SHOWING_URL = "https://www.cinema.com.hk/en/movie/ticketing"
BROADWAY_COMING_SOON_URL = "https://www.cinema.com.hk/en/movie/upcoming"

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

# Words to keep lowercase unless they appear at the start or end of a title
LOWERCASE_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from",
    "in", "into", "like", "near", "of", "off", "on", "onto",
    "or", "out", "over", "the", "to", "up", "upon", "with"
}

# Standard tech/cinema terms to preserve uppercase
PRESERVE_UPPERCASE = {"IMAX", "4DX", "CGS", "3D", "2D", "BTS"}


def to_title_case(text):
    """Formats text to Proper Title Case while keeping prepositions lowercase 
    and preserving cinema acronyms (IMAX, 4DX, CGS, BTS, etc.)."""
    if not text:
        return ""

    words = re.findall(r"[\w']+|[^\w\s]", text)
    formatted_words = []

    for i, word in enumerate(words):
        upper_word = word.upper()
        clean_word = word.lower()

        if upper_word in PRESERVE_UPPERCASE:
            formatted_words.append(upper_word)
        elif not word.isalnum():
            formatted_words.append(word)
        elif i == 0 or i == len(words) - 1:
            formatted_words.append(word.capitalize())
        elif clean_word in LOWERCASE_WORDS:
            formatted_words.append(clean_word)
        else:
            formatted_words.append(word.capitalize())

    result = ""
    for token in formatted_words:
        if token in "':-–—!?,.()[]":
            result = result.rstrip() + token
        elif result and result[-1] in "([{":
            result += token
        else:
            result = f"{result} {token}".strip() if result else token

    return result


def is_movie_title(text):
    if not text:
        return False
    clean_text = (
        text.replace("Emperor:", "")
        .replace("MCL:", "")
        .replace("Broadway:", "")
        .strip()
    )
    for pattern in PROMO_KEYWORDS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False
    return len(clean_text) > 0


def load_seen_movies():
    if os.path.exists(SEEN_MOVIES_FILE):
        try:
            with open(SEEN_MOVIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"now_showing": [], "coming_soon": []}


def save_seen_movies(seen_data):
    with open(SEEN_MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())


def build_discord_fields(section_title, titles, max_len=900):
    """Splits movie lists into standard fields that stay safely under 1,024 chars."""
    fields = []
    current_lines = []
    current_length = 0
    part = 1

    for title in titles:
        line = f"• {title}"
        if current_length + len(line) + 1 > max_len:
            field_name = section_title if part == 1 else f"{section_title} (Part {part})"
            fields.append({
                "name": field_name,
                "value": "\n".join(current_lines)
            })
            current_lines = [line]
            current_length = len(line)
            part += 1
        else:
            current_lines.append(line)
            current_length += len(line) + 1

    if current_lines:
        field_name = section_title if part == 1 else f"{section_title} (Part {part})"
        fields.append({
            "name": field_name,
            "value": "\n".join(current_lines)
        })

    return fields


def send_discord_notification(new_now_showing, new_coming_soon):
    if not DISCORD_WEBHOOK_URL:
        print("[Warning] DISCORD_WEBHOOK_URL environment variable is NOT set.")
        return

    all_fields = []
    if new_now_showing:
        all_fields.extend(build_discord_fields("🎬 New Now Showing", new_now_showing))

    if new_coming_soon:
        all_fields.extend(build_discord_fields("⏳ New Coming Soon", new_coming_soon))

    if not all_fields:
        return

    # Chunk fields across multiple Discord messages to stay well under the 6,000 char total limit per embed
    MAX_CHAR_PER_PAYLOAD = 4500
    payload_batches = []
    
    current_batch = []
    current_length = 0

    for field in all_fields:
        field_size = len(field["name"]) + len(field["value"])
        if current_length + field_size > MAX_CHAR_PER_PAYLOAD or len(current_batch) >= 10:
            payload_batches.append(current_batch)
            current_batch = [field]
            current_length = field_size
        else:
            current_batch.append(field)
            current_length += field_size

    if current_batch:
        payload_batches.append(current_batch)

    total_batches = len(payload_batches)
    for index, batch in enumerate(payload_batches, 1):
        title = "🎭 New Movies Detected!"
        if total_batches > 1:
            title += f" ({index}/{total_batches})"

        payload = {
            "embeds": [
                {
                    "title": title,
                    "color": 3447003,
                    "fields": batch,
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
                print(f"Successfully delivered Discord notification chunk {index}/{total_batches}!")
            else:
                print(f"[Error] Discord API status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[Error] Failed to execute Discord request: {e}")


def _extract_emperor_titles(page):
    """Internal helper to extract movie titles from Emperor Cinemas page."""
    page.wait_for_selector(".line-clamp-6", state="attached", timeout=20000)
    title_elements = page.query_selector_all("div.hover-mask div.line-clamp-6.text-ellipsis")
    
    titles = []
    for el in title_elements:
        raw_title = el.inner_text().strip()
        if is_movie_title(raw_title):
            clean_title = raw_title.replace("Emperor Cinemas:", "").strip()
            formatted_title = f"Emperor Cinemas: {to_title_case(clean_title)}"
            if formatted_title not in titles:
                titles.append(formatted_title)
    return titles


def fetch_emperor_movies(page):
    """Fetches both 'Now Showing' and 'Coming Soon' movies from Emperor Cinemas."""
    now_showing = []
    coming_soon = []

    try:
        page.goto(EMPEROR_URL, wait_until="domcontentloaded", timeout=60000)

        # 1. Scrape Now Showing (default view)
        now_showing = _extract_emperor_titles(page)

        # 2. Click the 'COMING SOON' tab and scrape Coming Soon
        coming_soon_btn = page.locator('div[data-text="COMING SOON"]').or_(page.locator('text="COMING SOON"'))
        if coming_soon_btn.count() > 0:
            coming_soon_btn.first.click()
            page.wait_for_timeout(2000)  # Allow dynamic content to load
            coming_soon = _extract_emperor_titles(page)
        else:
            print("[Warning] Emperor Cinemas: 'COMING SOON' tab trigger not found.")

    except Exception as e:
        print(f"[Error] Failed scraping Emperor Cinemas: {e}")

    return {"now_showing": now_showing, "coming_soon": coming_soon}


def fetch_mcl_movies(page, url, prefix="MCL:"):
    movies = []
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_selector(".movies-container .movie-container mark", state="attached", timeout=20000)
        title_elements = page.query_selector_all(
            ".movies-container .movie-container mark"
        )

        for el in title_elements:
            raw_title = el.inner_text().strip()
            if is_movie_title(raw_title):
                formatted_title = f"{prefix} {to_title_case(raw_title)}"
                if formatted_title not in movies:
                    movies.append(formatted_title)
    except Exception as e:
        print(f"[Error] Failed scraping MCL url ({url}): {e}")

    return movies


def fetch_broadway_now_showing(page):
    now_showing = []
    page.goto(BROADWAY_NOW_SHOWING_URL, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_selector("#mobile-movie-show p.font-semibold", state="attached", timeout=20000)
        title_elements = page.query_selector_all(
            "#mobile-movie-show a div p.font-semibold"
        )

        for el in title_elements:
            raw_title = el.inner_text().strip()
            if is_movie_title(raw_title):
                formatted_title = f"Broadway: {to_title_case(raw_title)}"
                if formatted_title not in now_showing:
                    now_showing.append(formatted_title)
    except Exception as e:
        print(f"[Error] Failed scraping Broadway Now Showing: {e}")

    return now_showing


def fetch_broadway_coming_soon(page):
    coming_soon = []
    page.goto(BROADWAY_COMING_SOON_URL, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_selector("a[href*='/en/movie/'] img[alt]", state="attached", timeout=20000)
        img_elements = page.query_selector_all("a[href*='/en/movie/'] img[alt]")

        for el in img_elements:
            raw_title = el.get_attribute("alt")
            if raw_title:
                raw_title = raw_title.strip()
                if is_movie_title(raw_title):
                    formatted_title = f"Broadway: {to_title_case(raw_title)}"
                    if formatted_title not in coming_soon:
                        coming_soon.append(formatted_title)
    except Exception as e:
        print(f"[Error] Failed scraping Broadway Coming Soon: {e}")

    return coming_soon


def fetch_all_live_movies():
    now_showing = []
    coming_soon = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Fetch Emperor Cinemas (Now Showing & Coming Soon)
        emperor_movies = fetch_emperor_movies(page)
        now_showing.extend(emperor_movies["now_showing"])
        coming_soon.extend(emperor_movies["coming_soon"])

        # 2. Fetch MCL Now Showing
        mcl_now = fetch_mcl_movies(page, MCL_NOW_SHOWING_URL)
        now_showing.extend(mcl_now)

        # 3. Fetch MCL Coming Soon
        mcl_soon = fetch_mcl_movies(page, MCL_COMING_SOON_URL)
        coming_soon.extend(mcl_soon)

        # 4. Fetch Broadway Now Showing
        broadway_now = fetch_broadway_now_showing(page)
        now_showing.extend(broadway_now)

        # 5. Fetch Broadway Coming Soon
        broadway_soon = fetch_broadway_coming_soon(page)
        coming_soon.extend(broadway_soon)

        browser.close()

    return {"coming_soon": coming_soon, "now_showing": now_showing}


if __name__ == "__main__":
    current_data = fetch_all_live_movies()
    seen_data = load_seen_movies()

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
            f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' entries."
        )
        send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found since last run.")

    save_seen_movies(current_data)
    print(f"Updated {SEEN_MOVIES_FILE} successfully.")
