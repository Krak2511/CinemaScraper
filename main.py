import json
import os
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
    if len(cleaned) < 2:
        return ""
    return cleaned


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
    """Renders Emperor's SPA page via Playwright and parses Swiper carousel slides."""
    coming_soon, now_showing = [], []
    url = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Get full dynamic HTML content post-render
            content = page.content()
            soup = BeautifulSoup(content, "html.parser")

            # Extract movies from non-duplicated Swiper carousel slides
            slides = soup.select(".swiper-slide:not(.swiper-slide-duplicate)")
            for slide in slides:
                img_tag = slide.find("img")
                if img_tag:
                    img_url = img_tag.get("src", "")

                    # Extract title from the image path/filename
                    filename = img_url.split("/")[-1].split("?")[0]
                    raw_title = filename.rsplit(".", 1)[0]
                    cleaned = clean_title(raw_title)

                    if (
                        cleaned
                        and cleaned not in now_showing
                        and "Emperor" not in cleaned
                    ):
                        now_showing.append(cleaned)

            # Fallback text extractors if carousel slide titles are empty
            if not now_showing:
                titles = page.locator(
                    ".film_title, .movie_title, .film-name, .title, h3, h4"
                ).all_inner_texts()
                for title in titles:
                    cleaned = clean_title(title)
                    if (
                        cleaned
                        and cleaned not in now_showing
                        and "Emperor" not in cleaned
                    ):
                        now_showing.append(cleaned)

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
