# AI Features

> Last verified: 2026-05-04 | Source of truth: this doc + the code it references

Snugd uses Anthropic Claude for scoring/comparison/synthesis and OpenAI Whisper for voice-note transcription. Free users get heuristic scoring; Pro users get Claude on every flow.

## Quick Commands

```bash
# Required env
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

# Hit score-batch directly
curl -X POST http://localhost:8000/api/search/score-batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "apartment_ids": ["apt_1", "apt_2"],
    "search_context": {"city": "NYC", "budget": 3500, "bedrooms": 1, "bathrooms": 1, "property_type": "Apartment", "move_in_date": "2026-06-01"}
  }'
```

## Architecture

```
Frontend search submit
   │
   ▼
POST /api/search          → heuristic-scored results returned immediately (< 200 ms)
   │
   ▼
Frontend renders results, then calls
POST /api/search/score-batch (≤ 10 IDs)  → Claude Haiku → AI score, reasoning, highlights
   │
   ▼
Frontend re-sorts by AI match_score (recent fix d862b7f)
```

- **Provider stack**: Anthropic Messages API (sync SDK wrapped via `asyncio.to_thread`); OpenAI Whisper for audio.
- **Concurrency**: `asyncio.Semaphore(5)` declared in `apartment_service.py:20`; used by the in-flight search-time scoring path.
- **Timeouts**: 15 s on the in-search Claude call; **45 s** on the comparison call (Sonnet needs more headroom).
- **Score-batch endpoint** in `main.py:280–340` does **not** use the semaphore or `asyncio.wait_for` — it relies on a broad `except` returning `{"scores": []}`. Worth knowing if you're tuning concurrency.
- **Prompt caching**: only the **system prompt** is cached (`cache_control: ephemeral`). Listings JSON is sent fresh every call, so cache hits amortize the system tokens only.
- **Fallback**: any exception → heuristic score path (`scoring_service.py`).

## Models

Pinned IDs in `claude_service.py`:

| Constant | Model | Used for |
|----------|-------|----------|
| `FAST` | `claude-haiku-4-5-20251001` | scoring, emails, day plan, note enhancement |
| `DEEP` | `claude-sonnet-4-5-20250929` | comparison head-to-head, decision brief |

Whisper: `whisper-1` (`response_format="text"`).

## ClaudeService Methods

### `score_apartments(city, budget, bedrooms, bathrooms, property_type, move_in_date, other_preferences, apartments) -> list`
- Model: Haiku.
- Inputs: search criteria + up to 10 listings (caller enforces).
- Output: `[{apartment_id, match_score (0–100), reasoning, highlights[]}]`.
- Called from: `POST /api/search/score-batch` (`main.py`), and during initial search if AI is requested.
- Fallback: caller catches any exception and returns the heuristic-scored list unchanged.

### `compare_apartments_with_analysis(apartments, search_context) -> dict`
- Model: Sonnet (45 s timeout, semaphore-wrapped).
- Inputs: 2–3 apartments + search context.
- Output: `{winner_id, summary, category_scores: {value, space, amenities, location, ...}, per_apartment: [{id, strengths, concerns}]}`.
- Called from: `POST /api/apartments/compare` for Pro users.
- Fallback: returns a basic non-AI comparison table.

### `generate_inquiry_email(apartment, user_context) -> str`
- Model: Haiku.
- Inputs: listing details, user move-in/preferences, tour record.
- Output: full email body referencing specific listing details and asking smart questions about missing info (sqft not listed, pet policy unclear, etc.).
- Called from: `POST /api/tours/{tour_id}/inquiry-email`. Persists to `tour_pipeline.inquiry_email_draft`.
- Fallback: 503 with explanatory message; UI shows "Try again" CTA.

### `generate_day_plan(tours_for_day) -> dict`
- Model: Haiku.
- Inputs: tours scheduled the same day with addresses + scheduled times.
- Output: `{ordered_tour_ids, travel_estimates, tips}`.
- Called from: `POST /api/tours/day-plan` (requires 2+ same-day tours).

### `generate_decision_brief(toured_tours, search_context) -> dict`
- Model: Sonnet.
- Inputs: toured tours with their notes/tags/ratings + the user's current search context (passed in per recent fix `d92640f`).
- Output: per-apartment cards (`strengths`, `concerns`, `top_pick` flag) + final recommendation paragraph.
- Called from: `POST /api/tours/decision-brief` (requires 2+ tours in `toured`/`deciding`).

### `enhance_note(raw_text) -> dict`
- Model: Haiku.
- Inputs: raw transcribed or typed note.
- Output: `{cleaned_text, suggested_tags: [{label, sentiment}]}` — strips filler, structures observations, suggests pro/con tags.
- Called from: `POST /api/tours/{tour_id}/enhance-note`, and chained automatically from `tasks/transcription_tasks.py::enhance_voice_note` for Pro users after transcription.

### `prepare_apartment_for_scoring(apt) -> dict` (helper)
- No AI call. Trims/serializes a listing for inclusion in a Claude prompt.

Internal: `_log_usage`, `_strip_code_block`, `_parse_*_response` handle markdown-fenced JSON output and token logging.

## Whisper Transcription Pipeline

1. `POST /api/tours/{tour_id}/notes/voice` — multipart audio upload (max 5 MB).
2. Backend uploads to S3 at `tours/{user_id}/{tour_id}/voice/{uuid}.{ext}`, creates a `tour_notes` row with `status=transcribing`, returns 202.
3. Celery task `transcribe_voice_note` (max 2 retries, 30 s delay) pulls the audio.
4. `WhisperService.transcribe_from_s3` calls Whisper (`whisper-1`, `response_format="text"`).
5. Updates `tour_notes.content` and `status=transcribed`.
6. **Pro tier**: chains to `enhance_voice_note` → `ClaudeService.enhance_note` → updates note with cleaned text + suggested tags.
7. Frontend polls (or subscribes via Supabase realtime) and replaces the placeholder.

Voice notes show with a microphone icon; typed notes with a pencil icon.

## Heuristic Scoring (free tier + AI fallback)

`scoring_service.py` weighted blend (sum = 100):

| Component | Weight | Notes |
|-----------|--------|-------|
| Budget | 30% | Strict — score = 0 at >10% over budget |
| Freshness | 20% | Decays with `last_seen_at` age |
| Data quality | 15% | Uses the apartment's quality score (0–100) |
| Amenity match | 20% | 15 keyword categories vs `other_preferences` |
| Space fit | 15% | Beds exact, baths at-least, sqft proximity |

`score_to_label(score)` maps to `Excellent / Great / Good / Fair`.

## Token & Cost Considerations

- Haiku is the default for any user-facing latency-sensitive path; Sonnet is reserved for synthesis tasks where the quality lift justifies ~5× the per-token cost.
- Prompt caching saves ~40% of input tokens on the system prompt across batched calls within the cache window.
- Search uses a two-pass design (heuristic-then-AI) so the user sees results immediately and only pays for AI if they scroll/engage.

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| `{"scores": []}` from score-batch | Any exception in Claude path; check API key, model availability, and that `search_context` is well-formed |
| Whisper job stuck | Celery worker not running, or S3 credentials missing; check task status in Flower / logs |
| Comparison times out | Sonnet hit the 45 s ceiling — usually means listings are too verbose; the call returns the basic comparison instead |
| Markdown-wrapped JSON parse failure | `_strip_code_block` handles `\`\`\`json` fences, but if Claude adds prose before the JSON, `_parse_*_response` retries with stricter extraction |
| 529 / 503 from Anthropic | Provider overload — fallback heuristic already kicks in for search; tours endpoints surface a "try again" message |
| Note enhancement not running | Only fires for Pro tier; check the user's `profiles.user_tier` |
