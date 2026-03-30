# Scraping Frequency & Market Configuration

Last updated: 2026-03-29

## Active Markets

| Tier | Frequency | Markets | Scrapes/Day | max_listings |
|------|-----------|---------|-------------|--------------|
| **Hot** | Every 12h | NYC, Boston, DC, Philadelphia (4) | **8** | 100 each |
| **Standard** | Every 24h | Pittsburgh, Baltimore, Newark, Jersey City, Cambridge, Arlington (6) | **6** | 100 each |
| **Cool** | Every 48h | Bryn Mawr, Charleston, New Orleans, Towson, State College (5 enabled) | **2.5** | 100 each |
| **Total** | | **15 active markets** | **16.5 scrapes/day** | **~1,650 listings/day** |

## Disabled Markets

These cool-tier markets are currently disabled to conserve Apify credits:

- Hoboken, NJ
- Stamford, CT
- New Haven, CT
- Providence, RI
- Richmond, VA
- Charlotte, NC
- Raleigh, NC
- Hartford, CT

## Cost Estimation

- Apify cost: ~$0.001 per listing (~1 cent per 10 listings)
- Estimated daily cost: ~$1.60/day at current configuration
- Verification checks (decay & verify) use HTTP only, no Apify credits

## Configuration Changes

To modify market settings, use the admin API:

```bash
# List all markets
curl http://localhost:8000/api/admin/data-collection/markets

# Disable a market
curl -X PUT http://localhost:8000/api/admin/data-collection/markets/{market_id} \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": false}'

# Change frequency
curl -X PUT http://localhost:8000/api/admin/data-collection/markets/{market_id} \
  -H "Content-Type: application/json" \
  -d '{"scrape_frequency_hours": 24}'

# Trigger immediate scrape
curl -X POST http://localhost:8000/api/admin/data-collection/markets/{market_id}/scrape
```

## History

| Date | Change |
|------|--------|
| 2026-03-29 | Added Charleston SC, New Orleans LA, Towson MD, State College PA (cool tier, 48h) |
| 2026-03-28 | Reduced frequencies (hot: 6→12h, standard: 12→24h, cool: 24→48h). Disabled 8 cool markets except Bryn Mawr to conserve Apify credits. |
| Initial | 19 East Coast markets, hot: 6h, standard: 12h, cool: 24h |
