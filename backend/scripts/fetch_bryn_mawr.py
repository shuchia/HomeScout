"""
Fetch Bryn Mawr apartments from Apify and save to apartments.json.
Usage: cd backend && python scripts/fetch_bryn_mawr.py
"""
import os
import json
import uuid
from apify_client import ApifyClient

# Load environment
from dotenv import load_dotenv
load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "maxcopell/apartments-scraper"
OUTPUT_FILE = "app/data/apartments.json"


def fetch_apartments():
    if not APIFY_TOKEN:
        print("Error: APIFY_API_TOKEN not set in .env")
        return

    print("Initializing Apify client...")
    client = ApifyClient(APIFY_TOKEN)

    # Run the actor
    print(f"Starting Apify actor: {ACTOR_ID}")
    print("Searching for apartments in Bryn Mawr, PA...")
    print("This may take 2-5 minutes...\n")

    # Input for maxcopell/apartments-scraper
    run_input = {
        "startUrls": [
            {"url": "https://www.apartments.com/bryn-mawr-pa/"}
        ],
        "maxItems": 100,
        "proxyConfiguration": {
            "useApifyProxy": True
        }
    }

    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)

        # Fetch results
        print("Fetching results...")
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        print(f"Found {len(items)} listings from Apify\n")

        if not items:
            print("No apartments found. Try expanding the search area.")
            return

        # Transform to our format
        apartments = []
        for item in items:
            apt = transform_listing(item)
            if apt:
                apartments.append(apt)

        print(f"Transformed {len(apartments)} valid apartments")

        # Save to JSON
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(apartments, f, indent=2)

        print(f"\nSaved to {OUTPUT_FILE}")
        print(f"Total apartments: {len(apartments)}")

        # Show sample
        if apartments:
            print("\nSample listing:")
            sample = apartments[0]
            print(f"  Address: {sample.get('address')}")
            print(f"  Rent: ${sample.get('rent')}/mo")
            print(f"  Beds/Baths: {sample.get('bedrooms')} bed / {sample.get('bathrooms')} bath")

    except Exception as e:
        print(f"Error: {e}")
        raise


def transform_listing(item):
    """Transform Apify listing to our apartment format."""
    try:
        # Extract address
        address = item.get("address") or item.get("streetAddress", "")
        city = item.get("city", "Bryn Mawr")
        state = item.get("state", "PA")
        zipcode = item.get("zipCode", item.get("postalCode", ""))

        if not address:
            return None

        full_address = f"{address}, {city}, {state} {zipcode}".strip()

        # Extract rent (handle ranges)
        rent = item.get("price") or item.get("rent") or item.get("minPrice")
        if isinstance(rent, str):
            rent = int(''.join(filter(str.isdigit, rent.split('-')[0])) or 0)
        rent = int(rent) if rent else 0

        if rent == 0:
            return None

        # Extract beds/baths
        beds = item.get("bedrooms") or item.get("beds") or 1
        if isinstance(beds, str):
            beds = int(''.join(filter(str.isdigit, beds)) or 1)

        baths = item.get("bathrooms") or item.get("baths") or 1
        if isinstance(baths, str):
            baths = float(''.join(c for c in baths if c.isdigit() or c == '.') or 1)

        # Extract sqft
        sqft = item.get("squareFeet") or item.get("sqft") or item.get("livingArea")
        if isinstance(sqft, str):
            sqft = int(''.join(filter(str.isdigit, sqft)) or 0)
        sqft = int(sqft) if sqft else None

        # Extract images
        images = item.get("images") or item.get("photos") or []
        if isinstance(images, list) and images:
            if isinstance(images[0], dict):
                images = [img.get("url") or img.get("src") for img in images if img.get("url") or img.get("src")]

        # Extract amenities
        amenities = item.get("amenities") or []
        if isinstance(amenities, str):
            amenities = [a.strip() for a in amenities.split(",")]

        return {
            "id": f"apt-{uuid.uuid4().hex[:8]}",
            "address": full_address,
            "city": city,
            "state": state,
            "zip_code": zipcode,
            "rent": rent,
            "bedrooms": int(beds),
            "bathrooms": float(baths),
            "sqft": sqft,
            "property_type": item.get("propertyType", "Apartment"),
            "available_date": item.get("availableDate", "Available Now"),
            "description": item.get("description", ""),
            "amenities": amenities[:10] if amenities else [],
            "images": images[:5] if images else ["https://picsum.photos/seed/apt/400/300"],
            "source": "apartments_com",
            "source_url": item.get("url", ""),
            "neighborhood": item.get("neighborhood", "Bryn Mawr"),
        }
    except Exception as e:
        print(f"Warning: Could not transform listing: {e}")
        return None


if __name__ == "__main__":
    fetch_apartments()
