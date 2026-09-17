import os
import json
import requests
from bs4 import BeautifulSoup

# Read Discord Webhook URL from GitHub Secrets environment variable
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "seen_movies.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def send_discord_notification(message):
    """Sends a formatted alert message directly to your Discord channel."""
    if not DISCORD_WEBHOOK_URL:
        print("Discord webhook URL not configured.")
        return

    payload = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to dispatch Discord message: {e}")

def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"coming_soon": [], "now_showing": []}

def save_current_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_mcl_movies():
    """Scrapes MCL Coming Soon and Now Showing pages."""
    coming_soon, now_showing = [], []
    
    # MCL Coming Soon
    try:
        res = requests.get("https://www.mclcinema.com/ComingSoon.aspx?visLang=2", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for title_tag in soup.select(".movie-title, .title, .film-name"):
            title = title_tag.get_text(strip=True)
            if title and title not in coming_soon:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching MCL Coming Soon: {e}")

    # MCL Now Showing
    try:
        res = requests.get("https://www.mclcinema.com/Ticketing.aspx?visLang=2", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for title_tag in soup.select(".movie-title, .title, .film-name"):
            title = title_tag.get_text(strip=True)
            if title and title not in now_showing:
                now_showing.append(title)
    except Exception as e:
        print(f"Error fetching MCL Now Showing: {e}")

    return coming_soon, now_showing

def fetch_broadway_movies():
    """Scrapes Broadway Circuit pages."""
    coming_soon, now_showing = [], []
    
    try:
        res = requests.get("https://www.cinema.com.hk/en/movie/upcoming", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for title_tag in soup.select(".movie-info .name, .film-title"):
            title = title_tag.get_text(strip=True)
            if title and title not in coming_soon:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching Broadway Upcoming: {e}")

    try:
        res = requests.get("https://www.cinema.com.hk/en/movie/ticketing", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for title_tag in soup.select(".movie-info .name, .film-title"):
            title = title_tag.get_text(strip=True)
            if title and title not in now_showing:
                now_showing.append(title)
    except Exception as e:
        print(f"Error fetching Broadway Ticketing: {e}")

    return coming_soon, now_showing

def fetch_emperor_movies():
    """Scrapes Emperor Cinemas pages."""
    coming_soon, now_showing = [], []
    
    try:
        res = requests.get("https://www.emperorcinemas.com/en/movie/coming_soon", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for title_tag in soup.select(".movie-name, .film-name, .title"):
            title = title_tag.get_text(strip=True)
            if title and title not in coming_soon:
                coming_soon.append(title)
    except Exception as e:
        print(f"Error fetching Emperor Coming Soon: {e}")

    try:
        res = requests.get("https://www.emperorcinemas.com/en/movie/now_showing", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for title_tag in soup.select(".movie-name, .film-name, .title"):
            title = title_tag.get_text(strip=True)
            if title and title not in now_showing:
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

    for chain_name, fetcher in chains.items():
        cs, ns = fetcher()
        
        # Check for new 'Coming Soon' announcements
        for movie in cs:
            full_entry = f"{chain_name}: {movie}"
            current_coming_soon.append(full_entry)
            if full_entry not in previous_state.get("coming_soon", []):
                alerts.append(f"📅 **Date Announced / Coming Soon**\n> **Chain:** {chain_name}\n> **Movie:** {movie}")

        # Check for movies going on sale / Now Showing
        for movie in ns:
            full_entry = f"{chain_name}: {movie}"
            current_now_showing.append(full_entry)
            if full_entry not in previous_state.get("now_showing", []):
                alerts.append(f"🎟️ **Tickets On Sale / Now Showing**\n> **Chain:** {chain_name}\n> **Movie:** {movie}")

    # Send alerts if updates are detected
    if alerts:
        for alert in alerts:
            send_discord_notification(alert)
        print(f"Sent {len(alerts)} alert(s) to Discord.")
    else:
        print("No new cinema additions detected.")

    # Save updated snapshot
    save_current_state({
        "coming_soon": current_coming_soon,
        "now_showing": current_now_showing
    })

if __name__ == "__main__":
    main()
