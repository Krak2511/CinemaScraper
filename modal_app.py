import os
import modal

# 1. Build image with Python dependencies & Playwright Chromium
image = (
    modal.Image.debian_slim()
    .pip_install("requests", "playwright")
    .run_commands("playwright install chromium --with-deps")
)

# 2. Define App and persistent Volume
app = modal.App("cinema-scraper")
volume = modal.Volume.from_name("scraper-state-volume", create_if_missing=True)


@app.function(
    image=image,
    volumes={"/root/data": volume},
    schedule=modal.Cron("*/30 * * * *"),
    secrets=[
        modal.Secret.from_dict(
            {"DISCORD_WEBHOOK_URL": os.environ.get("DISCORD_WEBHOOK_URL", "")}
        )
    ],
    timeout=300,
)
def run_scraper():
    import main

    print("🚀 Triggering cinema scraper on Modal...")

    # Reload volume to ensure state is fresh across runs
    volume.reload()

    # Point state tracking file to persistent storage path
    main.SEEN_MOVIES_FILE = "/root/data/seen_movies.json"

    current_data = main.fetch_all_live_movies()
    seen_data = main.load_seen_movies()

    current_now = current_data.get("now_showing", [])
    current_soon = current_data.get("coming_soon", [])

    seen_now = seen_data.get("now_showing", [])
    seen_soon = seen_data.get("coming_soon", [])

    # Identify genuine new entries
    new_now_showing = [m for m in current_now if m not in seen_now]
    new_coming_soon = [m for m in current_soon if m not in seen_soon]

    print(
        f"Scraped {len(current_now)} 'Now Showing' and {len(current_soon)} 'Coming Soon' titles."
    )

    if new_now_showing or new_coming_soon:
        print(
            f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' entries."
        )
        main.send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found.")

    # Merge current data into seen history without overwriting past entries
    updated_now_showing = list(dict.fromkeys(seen_now + current_now))
    updated_coming_soon = list(dict.fromkeys(seen_soon + current_soon))

    main.save_seen_movies(
        {
            "now_showing": updated_now_showing,
            "coming_soon": updated_coming_soon,
        }
    )

    # Commit changes to Modal Volume
    volume.commit()
    print("Execution complete.")
