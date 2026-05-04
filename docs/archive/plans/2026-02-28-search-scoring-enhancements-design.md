# Search Scoring Enhancements Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the unranked free-tier search with heuristic-scored results, improve Pro scoring by pre-ranking candidates for Claude, and reduce API costs with caching.

**Architecture:** Unified scoring pipeline — heuristic scoring runs on every search, Claude AI layers on top for Pro users. Free users see qualitative match labels; Pro users see precise AI scores.

**Tech Stack:** Python (FastAPI), Redis (caching), existing PostgreSQL fields (`data_quality_score`, `freshness_confidence`), Claude Sonnet API.

---

## Context

### Current State

The search has two completely separate paths:

- **Free/Anonymous:** Strict pass/fail filtering (exact budget ceiling, exact bedroom match). Results returned in arbitrary database order with no ranking. First 10 returned. Score shown as "Pro" badge.
- **Pro:** Same strict filtering, then an arbitrary 20 apartments sent to Claude for AI scoring (0-100). Claude returns match_score, reasoning, and highlights. Sorted by score, top 10 returned.

### Problems

1. Free users get no ranking — results are in database insertion order.
2. Budget filter is all-or-nothing — $1 over budget excludes the listing.
3. Claude receives arbitrary 20 apartments, not the best 20.
4. Identical Pro searches call Claude every time (no caching).
5. Claude receives truncated data (300-char descriptions, 15 amenities max).
6. No amenity-aware filtering from free-text preferences.

---

## Design

### Approach: Heuristic Pre-rank, Claude Re-rank

```
All users:  Filter (soft budget) → Heuristic score all → Sort by heuristic
Free:       Return top 10 with qualitative labels
Pro:        Take top 20 by heuristic → Check Redis cache → Claude re-scores → Sort by AI score → Cache → Return top 10
```

### 1. Heuristic Scoring Engine

New `ScoringService` in `backend/app/services/scoring_service.py`. Computes a 0-100 score for every apartment against search criteria. No AI calls — pure math.

**Scoring formula (weighted components):**

| Component | Weight | Logic |
|-----------|--------|-------|
| Budget fit | 30% | 100 if rent <= budget. Linear decay: 95 at 5% over, 80 at 10% over. 0 if >10% over. |
| Freshness | 20% | Based on `freshness_confidence` (0-100 in DB) and `last_seen_at` recency. |
| Data quality | 15% | Direct use of existing `data_quality_score` (0-100). |
| Amenity match | 20% | Parse `other_preferences` for keywords, match against listing's amenities array. Score = matched / requested * 100. |
| Space fit | 15% | Bonus for sqft (if available), exact bedroom match, bathroom overshoot. |

### 2. Budget Filter Relaxation

Expand from strict `rent <= budget` to `rent <= budget * 1.10`. Apartments over budget still appear but get penalized heavily in the budget fit scoring component (linear decay from 100 to 0 across the 0-10% overshoot range).

### 3. Amenity Keyword Extraction

Lightweight string-matching from `other_preferences` text. No AI needed.

**Keyword dictionary:**

```python
PREFERENCE_KEYWORDS = {
    "pet": ["pet-friendly", "pet friendly", "dogs allowed", "cats allowed", "pet"],
    "parking": ["parking", "garage", "covered parking", "ev charging"],
    "laundry": ["washer", "dryer", "in-unit laundry", "laundry"],
    "gym": ["gym", "fitness center", "fitness"],
    "pool": ["pool", "swimming"],
    "transit": ["transit", "metro", "subway", "bus", "train station"],
    "outdoor": ["balcony", "patio", "rooftop", "terrace", "yard"],
    "security": ["doorman", "concierge", "gated", "security"],
    "storage": ["storage", "closet space"],
    "utilities": ["utilities included", "wifi included", "water included"],
}
```

**How it works:**
1. Lowercase the `other_preferences` text.
2. Match against keyword dictionary — each matched category = one "requested amenity."
3. Check listing's `amenities` array for the same keywords.
4. Score = matched categories / requested categories * 100.

### 4. Richer Data to Claude

Remove artificial data truncation when sending apartments to Claude for Pro scoring.

**Current limits (removed):**
- Description truncated to 300 chars → now full text
- Amenities capped at 15 → now full list

**New fields added to Claude payload:**
- `neighborhood` — already in DB, helps Claude assess location quality
- `data_quality_score` — lets Claude factor in listing reliability
- `heuristic_score` — gives Claude our pre-ranking as a signal

Typical listing descriptions are 500-1500 chars. Sending 20 apartments with full descriptions adds ~5-8K input tokens per search (~$0.02 at Sonnet pricing), offset by Redis caching.

### 5. Claude Score Caching

Cache Claude's scoring results in Redis for Pro users.

**Cache key:** `claude_score:{SHA256(city + budget + beds + baths + type + date + preferences + sorted_apartment_ids)}`

**Behavior:**
- TTL: 1 hour
- Storage: JSON blob of Claude's full response (scores + reasoning + highlights)
- Hit: Skip Claude API call, return cached scores
- Miss: Call Claude, store result before returning
- Invalidation: TTL-based only

### 6. Qualitative Labels for Free Users

Free users see qualitative match labels instead of numeric scores.

**Score-to-label mapping:**
- 90-100 → "Excellent Match"
- 75-89 → "Great Match"
- 60-74 → "Good Match"
- 40-59 → "Fair Match"
- <40 → no label shown

**Response format for free/anonymous:**
```json
{
  "match_score": null,
  "match_label": "Great Match",
  "heuristic_score": 82,
  "reasoning": null,
  "highlights": []
}
```

`match_score` stays null (reserved for Claude AI). `match_label` is the qualitative string. `heuristic_score` is included for API consumers but the frontend displays the label.

### 7. Frontend Changes

**ApartmentCard.tsx** — display logic:
- `match_score != null` → "85% Match" (green/yellow/red badge, unchanged)
- `match_label != null` → "Great Match" (blue/green/gray badge, new)
- neither → "Pro" badge (fallback)

Label colors: Excellent=green, Great=blue, Good=gray-blue, Fair=gray.

**types/apartment.ts** — add `match_label?: string` and `heuristic_score?: number`.

**No changes to:** SearchForm, page layout, compare page.

---

## Files

**Create:**
- `backend/app/services/scoring_service.py` — heuristic scoring engine + amenity keyword extraction

**Modify:**
- `backend/app/services/apartment_service.py` — soft budget filter, unified pipeline, Claude cache
- `backend/app/services/claude_service.py` — remove data truncation, add new fields
- `backend/app/main.py` — unified search endpoint logic
- `backend/app/schemas.py` — add match_label, heuristic_score fields
- `frontend/components/ApartmentCard.tsx` — qualitative label display
- `frontend/types/apartment.ts` — new type fields

---

## Decisions Made

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Free-tier score display | Qualitative labels | Differentiates from Pro's AI scores, creates upsell incentive |
| Budget flexibility | 10% buffer, penalized | Prevents missing near-budget matches without surfacing irrelevant results |
| Claude caching | Redis, 1hr TTL | Reduces cost for repeated/similar searches |
| Pipeline architecture | Heuristic pre-rank, Claude re-rank | Claude gets best candidates instead of arbitrary ones |
| Data to Claude | Full description, full amenities | Removes arbitrary truncation, marginal cost increase offset by caching |
