import os
import json
import requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "seen_movies.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        print("Discord webhook URL missing.")
        return

    payload = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
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
    # Strip unnecessary whitespaces and newlines
    cleaned = " ".join(title.split())
    # Exclude common site UI text or button labels
    ignored_words = [
        "home", "ticketing", "coming soon", "now showing", "mcl club", 
        "cinema", "buy tickets", "more info", "trailer", "select cinema"
    ]
    if cleaned.lower() in ignored_words or len(cleaned) < 2:
        return ""
    return cleaned

def fetch_emperor_movies():
    """Scrapes Emperor's unified film listing page."""
    coming_soon, now_showing = [], []
    url = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Emperor group titles inside movie item containers
        movie_cards = soup.select(".film_item, .movie_item, .film_box, .film-item, [class*='film']")
        
        if not movie_cards:
            # Fallback to direct title targets
            movie_cards = soup.select(".film_title, .movie_title, .film-name, .movie-name")
            for card in movie_cards:
                title = clean_title(card.get_text())
                if title and title not in now_showing:
                    now_showing.append(title)
        else:
            for card in movie_cards:
                title_el = card.select_one(".film_title, .movie_title, .name, h3, h4")
                if title_el:
                    title = clean_title(title_el.get_text())
                    if title:
                        # Determine status based on parent tab or badge text
                        card_text = card.get_text().lower()
                        if "coming soon" in card_text or "upcoming" in card_text:
                            if title not in coming_soon:
                                coming_soon.append(title)
                        else:
                            if title not in now_showing:
                                now_showing.append(title)

    except Exception as e:
        print(f"Error fetching Emperor Cinemas: {e}")

    return coming_soon, now_showing

def fetch_mcl_movies():
    """Scrapes MCL Now Showing and Coming Soon pages."""
    coming_soon, now_showing = [], []
    
    # 1. MCL Now Showing
    try:
        url_ns = "https://www.mclcinema.com/NowShowing.aspx?visLang=2"
        res = requests.get(url_ns, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Target specific movie title containers within listing blocks
        for el in soup.select(".movie_name, .title_en, .film_title, .movie-title-text, .movie_list .title"):
            title = clean_title(el.get_text())
            if title and title not in now_showing:
                now_showing.append(title)
    except Exception as e:
        print(f"Error fetching MCL Now Showing: {e}")

    # 2. MCL Coming Soon
    try:
        url_cs = "https://www.mclcinema.com/ComingSoon.aspx?visLang=2"
        res = requests.get(url_cs, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        for el in soup.select(".movie_name, .title_en, .film_title, .movie-title-text, .movie_list .title"):
            title = clean_title(el.get_text())
            if title and title not in coming_soon:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching MCL Coming Soon: {e}")

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

    is_initial_run = len(previous_state.get("coming_soon", [])) == 0 and len(previous_state.get("now_showing", [])) == 0

    for chain_name, fetcher in chains.items():
        cs, ns = fetcher()
        
        for movie in cs:
            full_entry = f"{chain_name}: {movie}"
            current_coming_soon.append(full_entry)
            if not is_initial_run and full_entry not in previous_state.get("coming_soon", []):
                alerts.append(f"📅 **Date Announced / Coming Soon**\n> **Chain:** {chain_name}\n> **Movie:** {movie}")

        for movie in ns:
            full_entry = f"{chain_name}: {movie}"
            current_now_showing.append(full_entry)
            if not is_initial_run and full_entry not in previous_state.get("now_showing", []):
                alerts.append(f"🎟️ **Tickets On Sale / Now Showing**\n> **Chain:** {chain_name}\n> **Movie:** {movie}")

    if alerts:
        for alert in alerts:
            send_discord_notification(alert)
        print(f"Sent {len(alerts)} alert(s) to Discord.")
    elif is_initial_run:
        print("Initial state created.")
        send_discord_notification("✅ **Cinema Tracker Reset & Updated!** Now watching Emperor Cinemas and MCL Cinemas.")
    else:
        print("No new movie updates detected.")

    save_current_state({
        "coming_soon": current_coming_soon,
        "now_showing": current_now_showing
    })

if __name__ == "__main__":
    main()
