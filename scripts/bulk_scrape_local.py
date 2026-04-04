#!/usr/bin/env python3
"""
Bulk scrape Amazon products into the database using the local Flask app.

HOW TO USE
----------
1. Start the local Flask app in a separate terminal:
       cd /Users/jamie/Documents/University/ImpactTracker
       source venv/bin/activate
       python -m backend.api.app_production   (or however you run it locally)

   Make sure SCRAPERAPI_KEY is NOT set (unset it or leave it out of your .env)
   so the scraper uses direct requests from your home IP instead.

2. Run this script:
       python scripts/bulk_scrape_local.py

The script skips any URL that is already in the database (checked via the
cache hit the API returns). Results are written to a log file so you can
resume after a break.

ADDING MORE URLS
----------------
Edit the URLS list below. Use clean /dp/ASIN links — shorter is better.
"""

import requests
import time
import random
import json
import os
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
LOCAL_API   = "http://localhost:5000"
POSTCODE    = "SW1A 1AA"
DELAY_MIN   = 4     # seconds between requests (be polite to Amazon)
DELAY_MAX   = 9
LOG_FILE    = os.path.join(os.path.dirname(__file__), "bulk_scrape_results.jsonl")

# ── Product URLs ────────────────────────────────────────────────────────────────
# Curated list of diverse UK Amazon products across categories.
# Add / remove as needed. Clean /dp/ASIN format preferred.
URLS = [
    # ── Electronics ──────────────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B0CHX3QBCH",   # iPhone 15
    "https://www.amazon.co.uk/dp/B0BDHX8Z63",   # Samsung Galaxy S23
    "https://www.amazon.co.uk/dp/B09G9FPHY6",   # Apple AirPods Pro
    "https://www.amazon.co.uk/dp/B08N5WRWNW",   # Echo Dot 4th Gen
    "https://www.amazon.co.uk/dp/B07VGRJDFY",   # Kindle Paperwhite
    "https://www.amazon.co.uk/dp/B09B8W65QD",   # Apple Watch SE
    "https://www.amazon.co.uk/dp/B07XJ8C8F7",   # Anker USB-C charger
    "https://www.amazon.co.uk/dp/B00FLYWNYQ",   # TP-Link WiFi router

    # ── Kitchen & Home ────────────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B07YWZXV6R",   # Ninja air fryer
    "https://www.amazon.co.uk/dp/B00FLYWNYQ",   # KitchenAid stand mixer
    "https://www.amazon.co.uk/dp/B07NQPFQTB",   # Le Creuset cast iron pot
    "https://www.amazon.co.uk/dp/B071ZZ2HWJ",   # Instant Pot Duo
    "https://www.amazon.co.uk/dp/B07V4DM8XT",   # Nespresso Vertuo
    "https://www.amazon.co.uk/dp/B07X3HRDWC",   # Silicone baking mat
    "https://www.amazon.co.uk/dp/B07Q2GD1ZX",   # Glass meal prep containers
    "https://www.amazon.co.uk/dp/B01N9T1THZ",   # Stainless steel water bottle

    # ── Clothing & Fashion ────────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B07H3CTLXM",   # Levi's 501 jeans
    "https://www.amazon.co.uk/dp/B07WPXNLYV",   # Nike running trainers
    "https://www.amazon.co.uk/dp/B07XJ9R6SM",   # The North Face fleece
    "https://www.amazon.co.uk/dp/B08KGVJ9VX",   # Cotton t-shirt pack
    "https://www.amazon.co.uk/dp/B09BRV3MQ1",   # Wool socks

    # ── Sports & Outdoors ─────────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B08H93ZRK5",   # Yoga mat
    "https://www.amazon.co.uk/dp/B07CVF11ZN",   # Donner acoustic guitar
    "https://www.amazon.co.uk/dp/B08GTV1J83",   # Resistance bands set
    "https://www.amazon.co.uk/dp/B07B5KMY4M",   # Hydro Flask bottle
    "https://www.amazon.co.uk/dp/B07HFP3XZQ",   # Foam roller

    # ── Furniture & Home Office ───────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B08KH7SR9W",   # Standing desk
    "https://www.amazon.co.uk/dp/B07JFG1B9D",   # Ergonomic office chair
    "https://www.amazon.co.uk/dp/B08JDPRRPZ",   # Bamboo desk organiser
    "https://www.amazon.co.uk/dp/B07VHZ8T8X",   # Monitor stand

    # ── Beauty & Personal Care ────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B07GVHZWBK",   # Electric toothbrush
    "https://www.amazon.co.uk/dp/B00BTXGLCK",   # Bamboo toothbrush pack
    "https://www.amazon.co.uk/dp/B08GWDG4MF",   # Reusable cotton pads
    "https://www.amazon.co.uk/dp/B09B1YTJYX",   # Shampoo bar

    # ── Toys & Kids ───────────────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B07XKX8KFG",   # LEGO set
    "https://www.amazon.co.uk/dp/B07BNFWV8V",   # Wooden building blocks
    "https://www.amazon.co.uk/dp/B08P16KXHV",   # Silicone bath toys

    # ── Garden & DIY ─────────────────────────────────────────────────────────
    "https://www.amazon.co.uk/dp/B07MJ2Y56R",   # Stainless steel garden tools
    "https://www.amazon.co.uk/dp/B07BKSBLFD",   # Terracotta plant pots
    "https://www.amazon.co.uk/dp/B07ZYLT76Y",   # Bamboo plant labels

    # ── Books & Media (low CO₂ for baseline) ─────────────────────────────────
    "https://www.amazon.co.uk/dp/0241952743",    # Paperback book
]

# ── Helpers ─────────────────────────────────────────────────────────────────────

def log_result(entry: dict):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

def already_logged(url: str) -> bool:
    """Skip URLs we successfully scraped in a previous run."""
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("url") == url and entry.get("status") == "ok":
                    return True
            except Exception:
                pass
    return False

def scrape_one(url: str) -> dict:
    try:
        resp = requests.post(
            f"{LOCAL_API}/estimate_emissions",
            json={"amazon_url": url, "postcode": POSTCODE, "include_packaging": True},
            timeout=45,
        )
        data = resp.json()
        if not resp.ok:
            return {"url": url, "status": "error", "reason": data.get("error", str(resp.status_code))}

        title = data.get("title", "?")
        cache  = data.get("cache_hit", False)
        mat    = data.get("data", {}).get("attributes", {}).get("material_type", "?")
        origin = data.get("data", {}).get("attributes", {}).get("country_of_origin", "?")
        score  = data.get("data", {}).get("attributes", {}).get("eco_score_ml", "?")
        return {
            "url": url, "status": "ok", "title": title,
            "material": mat, "origin": origin, "eco_score": score,
            "cached": cache, "ts": datetime.utcnow().isoformat(),
        }
    except requests.exceptions.ConnectionError:
        return {"url": url, "status": "error", "reason": "Flask not running — start the local server first"}
    except Exception as e:
        return {"url": url, "status": "error", "reason": str(e)}


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    total   = len(URLS)
    done    = 0
    skipped = 0
    failed  = 0

    print(f"\n{'='*60}")
    print(f"  Bulk scrape — {total} URLs")
    print(f"  Local API : {LOCAL_API}")
    print(f"  Log file  : {LOG_FILE}")
    print(f"{'='*60}\n")

    for i, url in enumerate(URLS, 1):
        prefix = f"[{i:>3}/{total}]"

        if already_logged(url):
            print(f"{prefix} ⏭  SKIP (already scraped)  {url}")
            skipped += 1
            continue

        print(f"{prefix} 🔍 Scraping…  {url}")
        result = scrape_one(url)
        log_result(result)

        if result["status"] == "ok":
            cached_tag = " (cache)" if result.get("cached") else ""
            print(f"{prefix} ✅ {result['title'][:55]:<55}  "
                  f"mat={result['material']:<18} origin={result['origin']:<15} "
                  f"score={result['eco_score']}{cached_tag}")
            done += 1
        else:
            reason = result.get("reason", "unknown error")
            print(f"{prefix} ❌ FAILED — {reason}")
            if "Flask not running" in reason:
                print("\n⚠️  Cannot reach localhost:5000. "
                      "Start the Flask app first then re-run this script.\n")
                break
            failed += 1

        # Random delay only if we actually hit the network (not cached)
        if not result.get("cached") and result["status"] == "ok":
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            print(f"         ⏱  waiting {delay:.1f}s…")
            time.sleep(delay)

    print(f"\n{'='*60}")
    print(f"  Done: {done}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"  Full log: {LOG_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
