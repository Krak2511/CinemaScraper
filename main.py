import json
import re
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import requests

# ------------------------------------------------------------------------------
# 1. BROADWAY CINEMA
# ------------------------------------------------------------------------------
def get_broadway_movies():
    base_url = "https://www.cinema.com.hk"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    now_showing_url = f"{base_url}/en/movie/nowshowing"
    coming_soon_url = f"{base_url}/en/movie/comingsoon"

    def scrape_broadway_page(url):
        movies = []
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"Broadway: Failed to fetch {url} (Status {resp.status_code})")
                return movies
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            movie_nodes = soup.find_all('div', class_='movie-info')
            if not movie_nodes:
                movie_nodes = soup.find_all('div', class_=re.compile(r'movie', re.I))

            for node in movie_nodes:
                title_elem = node.find(['h2', 'h3', 'h4', 'div', 'a'], class_=re.compile(r'title|name', re.I))
                if not title_elem:
                    title_elem = node.find('a')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and title not in [m['title'] for m in movies]:
                        link = title_elem.get('href', '')
                        if link and not link.startswith('http'):
                            link = base_url + link
                        
                        img_elem = node.find('img')
                        poster = img_elem.get('src', '') if img_elem else ''
                        if poster and not poster.startswith('http'):
                            poster = base_url + poster

                        movies.append({
                            "title": title,
                            "link": link,
                            "poster": poster
                        })
        except Exception as e:
            print(f"Error scraping Broadway URL {url}: {e}")
        return movies

    return {
        "now_showing": scrape_broadway_page(now_showing_url),
        "coming_soon": scrape_broadway_page(coming_soon_url)
    }


# ------------------------------------------------------------------------------
# 2. MCL CINEMA
# ------------------------------------------------------------------------------
def get_mcl_movies():
    base_url = "https://www.mclcinema.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    now_showing_url = f"{base_url}/Movie.aspx?vis=1&lang=en"
    coming_soon_url = f"{base_url}/Movie.aspx?vis=2&lang=en"

    def scrape_mcl_page(url):
        movies = []
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"MCL: Failed to fetch {url} (Status {resp.status_code})")
                return movies

            soup = BeautifulSoup(resp.text, 'html.parser')
            movie_items = soup.find_all('div', class_=re.compile(r'movie-item|movieBox|film', re.I))
            if not movie_items:
                movie_items = soup.find_all('a', href=re.compile(r'MovieDetail', re.I))

            for item in movie_items:
                title = ""
                link = ""
                poster = ""

                if item.name == 'a':
                    link = item.get('href', '')
                    title = item.get_text(strip=True)
                    img = item.find('img')
                    if img:
                        poster = img.get('src', '')
                else:
                    title_elem = item.find(['div', 'span', 'h3', 'a'], class_=re.compile(r'title|name', re.I))
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    
                    link_elem = item.find('a', href=re.compile(r'MovieDetail', re.I))
                    if link_elem:
                        link = link_elem.get('href', '')
                        if not title:
                            title = link_elem.get_text(strip=True)
                    
                    img_elem = item.find('img')
                    if img_elem:
                        poster = img_elem.get('src', '')

                if title:
                    if link and not link.startswith('http'):
                        link = base_url + ('/' if not link.startswith('/') else '') + link
                    if poster and not poster.startswith('http'):
                        poster = base_url + ('/' if not poster.startswith('/') else '') + poster

                    if title not in [m['title'] for m in movies]:
                        movies.append({
                            "title": title,
                            "link": link,
                            "poster": poster
                        })
        except Exception as e:
            print(f"Error scraping MCL URL {url}: {e}")
        return movies

    return {
        "now_showing": scrape_mcl_page(now_showing_url),
        "coming_soon": scrape_mcl_page(coming_soon_url)
    }


# ------------------------------------------------------------------------------
# 3. EMPEROR CINEMAS (Playwright implementation with dynamic tab switching)
# ------------------------------------------------------------------------------
async def get_emperor_movies_async():
    url = "https://www.emperorcinemas.com/film?wapid=ECML_WEB_PROD_S_MPS"
    
    now_showing_movies = []
    coming_soon_movies = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        def parse_movies_from_html(html_content):
            soup = BeautifulSoup(html_content, 'html.parser')
            parsed = []
            
            # Common film card containers on Emperor Cinemas web page
            film_cards = soup.find_all('div', class_=re.compile(r'film-card|movie-card|filmItem|_', re.I))
            if not film_cards:
                film_cards = soup.find_all('a', href=re.compile(r'/film/', re.I))

            for card in film_cards:
                title = ""
                link = ""
                poster = ""

                # Try title parsing
                title_node = card.find(class_=re.compile(r'title|name|film-name', re.I))
                if title_node:
                    title = title_node.get_text(strip=True)

                link_node = card if card.name == 'a' else card.find('a', href=True)
                if link_node:
                    link = link_node.get('href', '')
                    if not title:
                        title = link_node.get_text(strip=True)

                img_node = card.find('img')
                if img_node:
                    poster = img_node.get('src') or img_node.get('data-src') or ''

                if title and len(title) > 1:
                    if link and not link.startswith('http'):
                        link = "https://www.emperorcinemas.com" + ('/' if not link.startswith('/') else '') + link
                    if poster and not poster.startswith('http'):
                        poster = "https://www.emperorcinemas.com" + ('/' if not poster.startswith('/') else '') + poster

                    if title not in [m['title'] for m in parsed]:
                        parsed.append({
                            "title": title,
                            "link": link,
                            "poster": poster
                        })
            return parsed

        try:
            # Load the main page (defaults to Now Showing)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # 1. Scrape NOW SHOWING
            content_now_showing = await page.content()
            now_showing_movies = parse_movies_from_html(content_now_showing)

            # 2. Click "COMING SOON" tab to fetch coming soon movies
            coming_soon_button = page.locator('div[data-text="COMING SOON"]').or_(page.locator('button:has-text("COMING SOON")'))
            
            if await coming_soon_button.count() > 0:
                await coming_soon_button.first.click()
                await page.wait_for_timeout(2000)
                await page.wait_for_load_state("networkidle")

                content_coming_soon = await page.content()
                coming_soon_movies = parse_movies_from_html(content_coming_soon)
            else:
                print("Emperor Cinemas: 'COMING SOON' button not found on page.")

        except Exception as e:
            print(f"Error scraping Emperor Cinemas via Playwright: {e}")

        await browser.close()

    return {
        "now_showing": now_showing_movies,
        "coming_soon": coming_soon_movies
    }


def get_emperor_movies():
    return asyncio.run(get_emperor_movies_async())


# ------------------------------------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------------------------------------
def main():
    print("Fetching Broadway Cinemas...")
    broadway_data = get_broadway_movies()

    print("Fetching MCL Cinemas...")
    mcl_data = get_mcl_movies()

    print("Fetching Emperor Cinemas...")
    emperor_data = get_emperor_movies()

    result = {
        "broadway": broadway_data,
        "mcl": mcl_data,
        "emperor": emperor_data
    }

    # Print or save result JSON
    print(json.dumps(result, indent=2, ensure_ascii=False))

    with open("movies.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
