"""
Run once before launch to populate initial apartment data.
Usage: cd backend && python -m scripts.initial_scrape
"""
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tasks.scrape_tasks import scrape_source


def main():
    print("Starting initial Bryn Mawr area scrape...")
    print("This may take a few minutes...\n")

    result = scrape_source.apply(
        args=("apartments_com",),
        kwargs={
            "cities": ["Bryn Mawr"],
            "state": "PA",
            "max_listings_per_city": 300,
        }
    ).get(timeout=600)

    print(f"\nScrape complete!")
    print(f"  Status: {result.get('status')}")
    print(f"  Total found: {result.get('total_found', 0)}")
    print(f"  New listings: {result.get('total_new', 0)}")
    print(f"  Duplicates: {result.get('total_duplicates', 0)}")
    print(f"  Errors: {result.get('total_errors', 0)}")

    if result.get('total_new', 0) < 20:
        print("\nWarning: Low inventory detected.")
        print("   Consider expanding to nearby areas:")
        print("   - Ardmore, PA")
        print("   - Haverford, PA")
        print("   - Wayne, PA")


if __name__ == "__main__":
    main()
