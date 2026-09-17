import os
import json
import requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "seen_movies.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
                # Verify structure isn't broken
                if "coming_soon" in data and "now_showing" in data:
                    return data
        except Exception as e:
            print(f"Error loading state file: {e}")
            
    return {"coming_soon": [], "now_showing": []}

def save_current_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def clean_title(title):
    """Clean up extracted string whitespace."""
    if not title:
        return ""
    return " ".join(title.split())

def fetch_mcl_movies():
    coming_soon, now_showing = [], []
    
    # MCL Coming Soon
    try:
        res = requests.get("https://www.mclcinema.com/ComingSoon.aspx?visLang=2", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        # Target title tags or image alt attributes where title is stored
        for el in soup.select("a, .movie-title, .title, h3, h4, img"):
            title = clean_title(el.get_text() or el.get("alt", ""))
            if len(title) > 2 and title not in coming_soon and "MCL" not in title:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching MCL Coming Soon: {e}")

    # MCL Now Showing
    try:
        res = requests.get("https://www.mclcinema.com/Ticketing.aspx?visLang=2", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for el in soup.select("a, .movie-title, .title, h3, h4, img"):
            title = clean_title(el.get_text() or el.get("alt", ""))
            if len(title) > 2 and title not in now_showing and "MCL" not in title:
                now_showing.append(title)
    except Exception as e:
        print(f"Error fetching MCL Now Showing: {e}")

    return coming_soon, now_showing

def fetch_broadway_movies():
    coming_soon, now_showing = [], []
    
    # Broadway Upcoming
    try:
        res = requests.get("https://www.cinema.com.hk/en/movie/upcoming", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for el in soup.select(".movie-info, .movie-title, .name, h2, h3, .film-title"):
            title = clean_title(el.get_text())
            if len(title) > 2 and title not in coming_soon:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching Broadway Upcoming: {e}")

    # Broadway Ticketing
    try:
        res = requests.get("https://www.cinema.com.hk/en/movie/ticketing", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for el in soup.select(".movie-info, .movie-title, .name, h2, h3, .film-title"):
            title = clean_title(el.get_text())
            if len(title) > 2 and title not in now_showing:
                now_showing.append(title)
    except Exception as e:
        print(f"Error fetching Broadway Ticketing: {e}")

    return coming_soon, now_showing

def fetch_emperor_movies():
    coming_soon, now_showing = [], []
    
    # Emperor Coming Soon
    try:
        res = requests.get("https://www.emperorcinemas.com/en/movie/coming_soon", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for el in soup.select(".movie-name, .film-name, .title, h2, h3, h4"):
            title = clean_title(el.get_text())
            if len(title) > 2 and title not in coming_soon and "Emperor" not in title:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching Emperor Coming Soon: {e}")

    # Emperor Now Showing
    try:
        res = requests.get("https://www.emperorcinemas.com/en/movie/now_showing", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for el in soup.select(".movie-name, .film-name, .title, h2, h3, h4"):
            title = clean_title(el.get_text())
            if len(title) > 2 and title not in now_showing and "Emperor" not in title:
                now_showing.append(title)
    except Exception as e:
        print(f"Error fetching Emperor Now Showing: {e}")

    return coming_soon, now_showing

def main():
    previous_state = load_previous_state()
    
    chains = {
        "MCL Cinemas": fetch_mcl_movies,
        "Broadway Circuit": fetch_broadway_movies,
        "Emperor Cinemas": fetch_emperor_movies,
    }
    
    current_coming_soon = []
    current_now_showing = []
    alerts = []

    # Detect if this is the very first time populating data
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

    # Send alerts if new entries found on subsequent runs
    if alerts:
        for alert in alerts:
            send_discord_notification(alert)
        print(f"Sent {len(alerts)} alert(s) to Discord.")
    elif is_initial_run:
        print("Initial run complete. Saved base list of movies to seen_movies.json.")
        send_discord_notification("✅ **Cinema Tracker Initialized!** Watching MCL, Broadway, and Emperor Cinemas for updates.")
    else:
        print("No new movie updates detected.")

    # Save updated snapshot
    save_current_state({
        "coming_soon": current_coming_soon,
        "now_showing": current_now_showing
    })

if __name__ == "__main__":
    main()
