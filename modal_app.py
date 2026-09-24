import os
import modal

# 1. Build image with Python dependencies & Playwright Chromium
# Mount local directory directly to the image using add_local_dir
image = (
    modal.Image.debian_slim()
    .pip_install("requests", "playwright")
    .run_commands("playwright install chromium --with-deps")
    .add_local_dir(".", remote_path="/root")
)

# 2. Define the Modal App and persistent Volume for state
app = modal.App("cinema-scraper")
volume = modal.Volume.from_name("scraper-state-volume", create_if_missing=True)


@app.function(
    image=image,
    # Persists seen_movies.json inside Modal cloud storage
    volumes={"/root/data": volume},
    # Triggers every 30 minutes with zero delays
    schedule=modal.Cron("*/30 * * * *"),
    secrets=[
        modal.Secret.from_dict({
            "DISCORD_WEBHOOK_URL": os.environ.get("DISCORD_WEBHOOK_URL", "")
        })
    ],
    timeout=300,
)
def run_scraper():
    import main

    print("🚀 Triggering cinema scraper on Modal...")

    # Point state tracking file to the persistent volume path
    main.SEEN_MOVIES_FILE = "/root/data/seen_movies.json"

    # Reload persistent volume to ensure latest file state
    volume.reload()

    live_cinemas = main.fetch_all_live_movies()
    seen_data = main.load_seen_movies()

    new_now_showing = []
    new_coming_soon = []
    updated_seen = {
        "now_showing": {},
        "coming_soon": {},
    }

    total_scraped_now = 0
    total_scraped_soon = 0

    for cinema_key in ["Emperor:", "MCL:", "Broadway:"]:
        for cat in ["now_showing", "coming_soon"]:
            scraped_list = live_cinemas[cinema_key][cat]
            previous_history = seen_data[cat].get(cinema_key, [])

            if scraped_list is None:
                # Scrape failed (e.g. MCL timeout): preserve history completely
                print(
                    f"[Warning] Preserving history for {cinema_key} ({cat}) due to scrape error."
                )
                updated_seen[cat][cinema_key] = previous_history
            else:
                if cat == "now_showing":
                    total_scraped_now += len(scraped_list)
                else:
                    total_scraped_soon += len(scraped_list)

                # Identify new entries not in history
                fresh_entries = [
                    m for m in scraped_list if m not in previous_history
                ]
                if cat == "now_showing":
                    new_now_showing.extend(fresh_entries)
                else:
                    new_coming_soon.extend(fresh_entries)

                # Union previous history + new scraped list
                updated_seen[cat][cinema_key] = list(
                    dict.fromkeys(previous_history + scraped_list)
                )

    print(
        f"Scraped {total_scraped_now} 'Now Showing' and {total_scraped_soon} 'Coming Soon' titles across active cinemas."
    )

    if new_now_showing or new_coming_soon:
        print(
            f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' entries."
        )
        main.send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found.")

    # Save structured history and commit volume changes
    main.save_seen_movies(updated_seen)
    volume.commit()
    print("Execution complete.")
