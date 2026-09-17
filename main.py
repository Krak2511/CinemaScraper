import json
import os
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "seen_movies.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# Ignore strings that are UI components, image formats, or generic site labels
INVALID_TITLES = [
    "format,webp",
    "webp",
    "banner",
    "emperor",
    "logo",
    "default",
    "poster",
    "carousel",
]


def send_discord_notification(message):
    """Sends webhook alerts directly to your Discord channel."""
    if not DISCORD_WEBHOOK_URL:
        print("Discord webhook URL missing.")
        return

    payload = {"content": message}
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL, json=payload, timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to dispatch Discord message: {e}")


def load_previous_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "coming_soon" in data and "now_showing" in data:
                    return data
        except Exception as e:
            print(f"Error loading state file: {e}")

    return {"coming_soon": [], "now_showing": []}


def save_current_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clean_title(title):
    if not title:
        return ""
    cleaned = " ".join(title.split())

    # Check against invalid substrings
    lowered = cleaned.lower()
    if (
        len(cleaned) < 2
        or any(invalid in lowered for invalid in INVALID_TITLES)
        or cleaned.isdigit()
    ):
        return ""

    return cleaned


def extract_title_from_url(img_url):
    """Extracts a readable movie name from image path if alt text is missing."""
    if not img_url:
        return ""

    # Strip query parameters (?format=webp, ?v=123, etc.)
    base_url = img_url.split("?")[0]

    # Get the last segment of the path
    filename = base_url.split("/")[-1]

    # Remove file extensions
    raw_title = re.sub(
        r"\.(jpg|jpeg|png|webp|gif|svg)$", "", filename, flags=re.IGNORECASE
    )

    # Convert encoded spaces/dashes to standard spaces
    raw_title = raw_title.replace("%20", " ").replace("-", " ").replace("_", " ")

    return clean_title(raw_title)


def fetch_mcl_movies():
    """Scrapes MCL directly via its mobile JSON API endpoints."""
    coming_soon, now_showing = [], []

    # MCL Now Showing API
    try:
        url_ns = "https://m.mclcinema.com/Ticketing/GetNowShowingList?lang=2"
        res = requests.get(url_ns, headers=HEADERS, timeout=15)
        if res.status_code == 200 and "json" in res.headers.get(
            "Content-Type", ""
        ):
            data = res.json()
            for movie in data.get("data", []):
                title = clean_title(
                    movie.get("MovieNameEn") or movie.get("MovieName")
                )
                if title and title not in now_showing:
                    now_showing.append(title)
        else:
            soup = BeautifulSoup(res.text, "html.parser")
            for el in soup.select(".movie-name, .film-title, .title"):
                title = clean_title(el.get_text())
                if title and title not in now_showing:
                    now_showing.append(title)
    except Exception as e:
        print(f"Error fetching MCL Now Showing: {e}")

    # MCL Coming Soon API
    try:
        url_cs = "https://m.mclcinema.com/Ticketing/GetUpcomingList?lang=2"
        res = requests.get(url_cs, headers=HEADERS, timeout=15)
        if res.status_code == 200 and "json" in res.headers.get(
            "Content-Type", ""
        ):
            data = res.json()
            for movie in data.get("data", []):
                title = clean_title(
                    movie.get("MovieNameEn") or movie.get("MovieName")
                )
                if title and title not in coming_soon:
                    coming_soon.append(title)
        else:
            soup = BeautifulSoup(res.text, "html.parser")
            for el in soup.select(".movie-name, .film-title, .title"):
                title = clean_title(el.get_text())
                if title and title not in coming_soon:
                    coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching MCL Coming Soon: {e}")

    return coming_soon, now_showing


def fetch_emperor_movies():
    """Renders Emperor's SPA page via Playwright and parses movie titles safely."""
    coming_soon, now_showing = [], []
    url = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

            # 1. Try extracting text labels directly from DOM cards/titles
            titles = page.locator(
                ".film_title, .movie_title, .film-name, .title, h3, h4"
            ).all_inner_texts()
            for title in titles:
                cleaned = clean_title(title)
                if cleaned and cleaned not in now_showing:
                    now_showing.append(cleaned)

            # 2. Parse Swiper slides with improved fallback detection
            content = page.content()
            soup = BeautifulSoup(content, "html.parser")
            slides = soup.select(".swiper-slide:not(.swiper-slide-duplicate)")

            for slide in slides:
                movie_title = ""

                # Check text tags inside slide
                text_tag = slide.select_one(
                    ".film_title, .movie_title, .film-name, h3, h4"
                )
                if text_tag:
                    movie_title = clean_title(text_tag.get_text())

                # Check img attributes (alt, title)
                img_tag = slide.find("img")
                if not movie_title and img_tag:
                    alt_text = img_tag.get("alt") or img_tag.get("title") or ""
                    movie_title = clean_title(alt_text)

                    # Extract title safely from URL if no alt text exists
                    if not movie_title:
                        img_url = img_tag.get("src", "")
                        movie_title = extract_title_from_url(img_url)

                if movie_title and movie_title not in now_showing:
                    now_showing.append(movie_title)

            browser.close()
    except Exception as e:
        print(f"Error fetching Emperor Cinemas via Playwright: {e}")

    return coming_soon, now_showing


def main():
    previous_state = load_previous_state()

    chains = {
        "MCL Cinemas": fetch_mcl_movies,
        "Emperor Cinemas": fetch_emperor_movies,
    }

    current_coming_soon = []
    current_now_showing = []
    alerts = []

    is_initial_run = (
        len(previous_state.get("coming_soon", [])) == 0
        and len(previous_state.get("now_showing", [])) == 0
    )

    for chain_name, fetcher in chains.items():
        cs, ns = fetcher()
        print(
            f"[{chain_name}] Found {len(cs)} Coming Soon, {len(ns)} Now"
            " Showing movies."
        )

        for movie in cs:
            full_entry = f"{chain_name}: {movie}"
            current_coming_soon.append(full_entry)
            if not is_initial_run and full_entry not in previous_state.get(
                "coming_soon", []
            ):
                alerts.append(
                    "📅 **Date Announced / Coming Soon**\n>"
                    f" **Chain:** {chain_name}\n> **Movie:** {movie}"
                )

        for movie in ns:
            full_entry = f"{chain_name}: {movie}"
            current_now_showing.append(full_entry)
            if not is_initial_run and full_entry not in previous_state.get(
                "now_showing", []
            ):
                alerts.append(
                    "🎟️ **Tickets On Sale / Now Showing**\n>"
                    f" **Chain:** {chain_name}\n> **Movie:** {movie}"
                )

    if alerts:
        for alert in alerts:
            send_discord_notification(alert)
        print(f"Sent {len(alerts)} alert(s) to Discord.")
    elif is_initial_run:
        print("Initial state created.")
        send_discord_notification(
            "✅ **Cinema Tracker Initialized!** Stored initial list of movies"
            " across MCL and Emperor."
        )
    else:
        print("No new movie updates detected.")

    save_current_state(
        {"coming_soon": current_coming_soon, "now_showing": current_now_showing}
    )


if __name__ == "__main__":
    main()
