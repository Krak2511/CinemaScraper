import json
import re
from bs4 import BeautifulSoup


def parse_movies(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Standard non-movie promotional tags to ignore
    promo_keywords = [
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
        # Clean prefix if scraped as "Emperor Cinemas: Movie Title"
        clean_text = text.replace("Emperor Cinemas:", "").strip()
        # Check against promo keywords
        for pattern in promo_keywords:
            if re.search(pattern, clean_text, re.IGNORECASE):
                return False
        return len(clean_text) > 0

    now_showing = []
    coming_soon = []

    # Target movie containers in Emperor Cinemas' DOM structure
    movie_cards = soup.find_all(
        ["div", "a"],
        class_=lambda c: c
        and ("film" in c or "movie" in c or "card" in c or "item" in c),
    )

    for card in movie_cards:
        # Extract title text
        title_el = card.find(
            ["h2", "h3", "h4", "div", "span"],
            class_=lambda c: c and ("title" in c or "name" in c),
        )
        title = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)

        if title and is_movie_title(title):
            formatted_title = (
                f"Emperor Cinemas: {title.replace('Emperor Cinemas:', '').strip()}"
            )

            # Determine section based on parent block/attributes
            parent_text = (
                card.find_parent(
                    ["section", "div"],
                    class_=lambda c: c and ("soon" in c or "showing" in c),
                )
                or ""
            )

            if "soon" in str(parent_text).lower():
                if formatted_title not in coming_soon:
                    coming_soon.append(formatted_title)
            else:
                if formatted_title not in now_showing:
                    now_showing.append(formatted_title)

    return {"coming_soon": coming_soon, "now_showing": now_showing}


# Load your saved HTML file and process
with open("Emperor Cinemas_2.html", "r", encoding="utf-8") as f:
    data = parse_movies(f.read())

print(json.dumps(data, indent=2, ensure_ascii=False))
