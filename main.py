import json
import re
from playwright.sync_api import sync_playwright

URL = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS"

# Standard non-movie promotional tags to ignore
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


def fetch_live_movies():
    now_showing = []
    coming_soon = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector(".line-clamp-6", timeout=20000)

        # Target the titles based on the live Tailwind structure
        title_elements = page.query_selector_all(
            "div.hover-mask div.line-clamp-6.text-ellipsis"
        )

        for el in title_elements:
            raw_title = el.inner_text().strip()

            if is_movie_title(raw_title):
                clean_title = raw_title.replace("Emperor Cinemas:", "").strip()
                formatted_title = f"Emperor Cinemas: {clean_title}"

                # Simple check to classify coming soon vs now showing based on element scope
                is_coming_soon = el.evaluate(
                    """node => {
                    const parent = node.closest('[class*="soon"], [id*="soon"]');
                    return parent !== null;
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
    data = fetch_live_movies()
    print(json.dumps(data, indent=2, ensure_ascii=False))
