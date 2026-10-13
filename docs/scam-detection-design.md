# Listing Scam Detection — design

> Status: design, nothing built. Supersedes the 2026-09-03 discussion thread,
> which lived only in session memory until now.

## Why this and not something else

The repository is open source and the feature list is not a moat. Every
candidate on it — lease analysis, roommate split, application assembly — is a
week of work for a competent team with modern tooling. Copying the code copies
the feature.

A **hook** pulls a stranger in without signup. A **moat** is what a competitor
still lacks after forking the repo. Moats live in what is hard to *assemble or
accumulate*: a corpus, a registry, per-jurisdiction plumbing.

Scam detection is the one candidate where the hook and the moat are the same
interaction. A stranger pastes a listing URL, gets a trust assessment with no
account, and shares it. The checks themselves are not the moat — anyone can
write a regex for "wire the deposit". The **confirmed-scam registry** is:
photo hashes, phone numbers, email addresses and phrasing from listings that
turned out to be fraudulent. It accrues on every free submission, and a forker
starts at zero.

Second place, and undervalued: a **landlord report card** built from
housing-court records and code violations. Public but scattered across county
systems with no APIs, and that awfulness *is* the barrier — it compounds county
by county. Scope narrow if it happens: Allegheny (Pitt) and Centre (Penn State)
only, sourced verbatim to public records with dates and links. Anything less is
a defamation problem.

## What ships first

Phase 1 is everything that works at today's corpus size, and the registry
schema so it compounds from day one.

| Signal | Source | Notes |
|---|---|---|
| Off-platform payment language | listing text | "wire", "Western Union", "Zelle before viewing", "I'm out of the country" |
| Contact analysis | listing contact fields | free email domain, area code inconsistent with the market, contact name absent |
| Below-market rent | our corpus | see below — a rank, not a threshold |
| Registry hit | our registry | phone / email / photo hash previously confirmed fraudulent |

Phase 2 is photo matching, which is the only signal that is coverage-bound.

## Below-market rent: use a percentile rank, not a distance

The original thread left "median/MAD or a percentile floor" open. Measured
against the live corpus (3,942 active listings, 41 usable `(city, bedrooms)`
groups covering 98% of them), `median − 3×MAD` is **inert**:

| group | n | median | MAD threshold | flagged |
|---|---|---|---|---|
| New York, 1BR | 260 | 4,905 | 968 | **0** |
| New York, 2BR | 191 | 5,750 | 251 | **0** |
| Boston, studio | 189 | 2,555 | 1,340 | **0** |
| Pittsburgh, 1BR | 186 | 1,217 | 551 | **0** |

Ten flags across 2,037 listings, none of them in the high-variance markets
where a too-good-to-be-true price is most plausible. Rent dispersion in NYC is
wide enough that three MADs below the median is below any real rent.

So: compute the listing's **percentile rank within its `(city, bedrooms)`
group** and treat it as a continuous feature. A listing at p1 is more
suspicious than one at p5; neither is damning alone. This is deliberately not a
boolean — by construction the 5th percentile flags 5% of every market, and the
cheapest twentieth of Pittsburgh is not fraud.

Two corpus facts this depends on, both now true and neither true three weeks
ago:

- **City names are canonical.** Comps keyed on `city` used to compute a
  separate median for `SAN FRANCISCO`, `Mc Kees Rocks` and `The Bronx`.
- **`rent` is honest.** It is `None` for a price-on-request floorplan rather
  than silently falling back to the building's figure, so unpriced listings
  drop out of the comp set instead of poisoning it.

Exclude price-on-request listings from both the comp set and the scoring.
Never use `min` as the floor: State College's minimum rent was literally $1
until a source check corrected it to $1,449.

## Photo matching (Phase 2)

Four image sets, and conflating them is how this goes wrong:

| Set | What it is | Role |
|---|---|---|
| **Reference corpus** | photos on already-scraped apartments.com listings | the known-legitimate set to match *against* |
| **Query images** | photos on the pasted suspect listing, fetched by us | the user uploads nothing |
| **Scam registry** | hashes of confirmed frauds | the compounding piece |
| **`tour_photos`** | the user's own photos of units they visited | **excluded** |

`tour_photos` is excluded deliberately: a user's photo of a real unit matching
that unit's listing photo is expected, not suspicious.

**Precision, not scale, is the hard part.** Known false-positive sources:

- **Our own duplicate rows.** apartments.com returns a building once per unit,
  so one property legitimately occupies several rows — `62 Boylston St` has
  five at different rents. Deduplication on the source property id collapsed
  15.6% of the corpus, but per-unit duplicates remain by design.
- **Portfolio-wide amenity photos.** The gym shot reused across forty
  buildings is the most-copied and least-distinctive image in the set. Filter
  or weight near zero.
- **Legitimate syndication** across listing sites.

So a photo match is a **join key, not a verdict**. It counts only when the
discriminators diverge: different street address, materially lower price,
different contact channel, off-platform payment language.

pHash is robust to rescaling and recompression, weak to cropping, mirroring and
overlays. It catches lazy copying, which is most of it, not all of it.

**Coverage.** Confirmed 2026-10-12: 3,860 of 3,942 listings carry images
(98%), median 6 each, **~22,400 URLs**, all on `images1.apartments.com`.
`images_cached` exists on the model but has never been populated — we hold
hotlink URLs, not bytes. A pHash backfill is therefore ~22k CDN fetches, and
those URLs rotate, so the hashing should start well before the feature does.

Phase 2 sits behind a State College deep sweep: the one market where
near-complete apartments.com coverage is realistically attainable, and the
student audience most exposed to rental fraud. NYC is a rounding error against
real inventory and always will be.

## The wording rule

"No match" renders as **"we could not verify this"** — never "this looks fine."

This is not a style preference. Every pipeline fault found in 2026 produced
output that looked like data: an Akamai 403 read as `verified`, a payload field
that moved read as "price on request", a rate-limited response read as "this
listing has no floorplans". A trust product that resolves *unknown* into
*reassuring* is the same bug with a user's deposit attached.

## Explicitly out of scope

- **Demographic or "vibe" matching** — "average age of residents", "your kind
  of place". That is steering by protected class under the Fair Housing Act,
  and strictly worse than the crime data already shelved in June.
- **Any verdict we cannot source.** A score is a claim about a named landlord
  or property. Everything shown traces to listing text, our own corpus, or a
  public record with a date and a link.

## Prerequisites — all now met

| Was blocking | Status |
|---|---|
| Corpus stale, scraping ~1 job/day | Fixed 2026-09-25; all 8 markets sweeping |
| "No pagination" | Misdiagnosed. Markets *exhaust* at `maxItems: 1000`; the ceiling was a config value |
| City names unnormalized | Fixed 2026-10-09; 95 strings collapsed to 91, zero collisions |
| `scrape_url()` unproven | Backs the live saved-listing check; ~$0.0005, goes through `api.apify.com` so Akamai is Apify's problem |

The add-by-URL wedge needs no new acquisition infrastructure. `scrape_url()`
already fetches an arbitrary apartments.com listing on demand.

## Open questions

1. **Registry seeding.** The registry is worthless empty and compounds only
   with submissions. Is there a public source — FTC complaints, r/Scams,
   university housing-office bulletins — worth a one-off import?
2. **Confirmation loop.** Who marks a listing "confirmed fraudulent"? Entries
   based on an unverified report are a defamation surface.
3. **Abuse.** A free no-signup endpoint that fetches arbitrary URLs is an SSRF
   and cost vector. Needs allow-listing to apartments.com and rate limiting
   before it is public.
