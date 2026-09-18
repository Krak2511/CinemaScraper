import modal

# 1. Build container image with Python dependencies & Playwright Chromium
image = (
    modal.Image.debian_slim()
    .pip_install("requests", "playwright")
    .run_commands("playwright install chromium --with-deps")
)

# 2. Define the Modal App and persistent Volume for state
app = modal.App("cinema-scraper")
volume = modal.Volume.from_name("scraper-state-volume", create_if_missing=True)

# 3. Mount repository files into the execution container
mount = modal.Mount.from_local_dir(".", remote_path="/root")

@app.function(
    image=image,
    mounts=[mount],
    # Persists seen_movies.json inside Modal cloud storage
    volumes={"/root/data": volume},
    # Triggers every 30 minutes with zero delays
    schedule=modal.Cron("*/30 * * * *"),
    secrets=[
        modal.Secret.from_dict({
            "DISCORD_WEBHOOK_URL": os.environ.get("DISCORD_WEBHOOK_URL", "")
        })
    ],
    timeout=300
)
def run_scraper():
    import os
    import json
    import main

    print("🚀 Triggering cinema scraper on Modal...")

    # Point state tracking file to the persistent volume path
    main.SEEN_MOVIES_FILE = "/root/data/seen_movies.json"

    current_data = main.fetch_all_live_movies()
    seen_data = main.load_seen_movies()

    new_now_showing = [
        m for m in current_data["now_showing"] if m not in seen_data["now_showing"]
    ]
    new_coming_soon = [
        m for m in current_data["coming_soon"] if m not in seen_data["coming_soon"]
    ]

    print(
        f"Scraped {len(current_data['now_showing'])} 'Now Showing' and {len(current_data['coming_soon'])} 'Coming Soon' titles."
    )

    if new_now_showing or new_coming_soon:
        print(
            f"Detected {len(new_now_showing)} new 'Now Showing' and {len(new_coming_soon)} new 'Coming Soon' entries."
        )
        main.send_discord_notification(new_now_showing, new_coming_soon)
    else:
        print("No new movies found.")

    main.save_seen_movies(current_data)
    # Commit changes to Modal persistent storage
    volume.commit()
    print("Execution complete.")
