# AI Performance Improvement Plan

**Goal:** Reduce Claude API latency, optimize token usage, and improve AI quality across search scoring, comparison analysis, and tour features.

---

## Current State (as of 2026-03-31)

| Feature | Model | Latency | Cache | Tokens/call |
|---------|-------|---------|-------|-------------|
| Search scoring (Pro) | Sonnet 4.5 | 3-5s | Redis 1hr TTL | ~4,500 (20 apts) |
| Compare analysis (Pro) | Sonnet 4.5 | 3-5s | None | ~2,500 (2-3 apts) |
| Inquiry email | Sonnet 4.5 | 2-3s | None | ~800 |
| Day plan | Sonnet 4.5 | 2-3s | None | ~1,000 |
| Note enhancement | Sonnet 4.5 | 1-2s | None | ~500 |
| Decision brief | Sonnet 4.5 | 3-4s | None | ~2,000 |

**Already implemented:**
- Prompt caching (`cache_control: ephemeral`) on all 6 Claude calls
- Redis score cache for search (1hr TTL)
- `asyncio.to_thread()` for all Claude calls (non-blocking)
- `prepare_apartment_for_scoring()` strips images before sending to Claude

---

## Phase 1: Latency Reduction (Week 1)

### 1.1 Use Haiku for Search Scoring

Search scoring produces structured JSON (scores 0-100) — Haiku handles this well at ~1s vs 3-5s for Sonnet.

**Change:** In `score_apartments()`, use `claude-haiku-4-5-20251001` instead of `claude-sonnet-4-5-20250929`.

**Expected:** 3-5s → 0.8-1.5s per search. ~75% latency reduction.

**Risk:** Slightly lower scoring nuance. Mitigate by keeping Sonnet for comparison analysis where depth matters.

### 1.2 Parallel Scoring for Large Result Sets

Currently sends up to 20 apartments in one Claude call. Split into two parallel batches of 10.

**Change:** In `get_top_apartments()`, split `apartments_to_score` into two halves, call Claude in parallel with `asyncio.gather()`, merge scores.

**Expected:** Two 10-apt calls at ~0.7s each (parallel) vs one 20-apt call at ~1.2s = ~40% latency win on large result sets.

### 1.3 Streaming for Compare Analysis

Compare analysis is the slowest user-facing Claude call. Stream the response so the frontend can show the winner immediately while category scores load.

**Changes:**
- Backend: Add `/api/apartments/compare/stream` endpoint using SSE (Server-Sent Events)
- Claude: Use `client.messages.stream()` instead of `client.messages.create()`
- Frontend: Parse SSE events, show winner card first, then category scores as they arrive

**Expected:** Perceived latency drops from 3-5s to <1s (winner visible within first chunk).

---

## Phase 2: Cost Optimization (Week 2)

### 2.1 Model Tiering

| Feature | Current | Proposed | Savings |
|---------|---------|----------|---------|
| Search scoring | Sonnet | Haiku | ~80% cost reduction |
| Compare analysis | Sonnet | Sonnet (keep) | — |
| Inquiry email | Sonnet | Haiku | ~80% cost reduction |
| Note enhancement | Sonnet | Haiku | ~80% cost reduction |
| Day plan | Sonnet | Haiku | ~80% cost reduction |
| Decision brief | Sonnet | Sonnet (keep) | — |

**Rule:** Use Haiku for structured/templated output. Use Sonnet for nuanced analysis and free-form reasoning.

### 2.2 Token Budget Tracking

Add per-request token logging to track actual usage:

```python
message = self.client.messages.create(...)
logger.info(f"Claude tokens: input={message.usage.input_tokens} "
            f"output={message.usage.output_tokens} "
            f"cache_read={message.usage.get('cache_read_input_tokens', 0)}")
```

Feed into CloudWatch custom metrics for cost dashboards.

### 2.3 Monthly Cost Projections

| Scenario | Searches/day | Compares/day | Monthly Cost |
|----------|-------------|--------------|-------------|
| Beta (50 users) | ~100 | ~20 | ~$15-25 |
| Growth (500 users) | ~1,000 | ~200 | ~$80-150 |
| Scale (5,000 users) | ~10,000 | ~2,000 | ~$500-1,000 |

With Haiku for scoring + Redis cache (est. 60% hit rate), actual costs will be ~40% of these numbers.

---

## Phase 3: Quality Improvement (Week 3-4)

### 3.1 Scoring Calibration

Current scoring is uncalibrated — what does "85% match" actually mean? Add calibration:

- Collect user feedback on search results (thumbs up/down on shown apartments)
- Compare Claude scores against user preference signals (favorites, tour pipeline adds)
- Adjust system prompt weighting based on which criteria users actually care about

### 3.2 Few-Shot Examples in Prompts

Add 2-3 example scorings to the system prompt as few-shot examples. These improve consistency and reduce hallucinated reasoning.

**Note:** Few-shot examples increase prompt size but with prompt caching, they're cached after the first call — no latency penalty.

### 3.3 Comparison Analysis Depth

Current compare prompt generates 1-3 custom categories. Improve by:
- Using search context to pre-select relevant categories (if user mentioned "pets", always include "Pet-Friendliness")
- Adding true cost breakdown to the comparison categories when available

---

## Phase 4: Operational Observability (Ongoing)

### 4.1 Metrics to Track

| Metric | Where | Alert Threshold |
|--------|-------|----------------|
| Claude API latency p95 | CloudWatch | > 8s |
| Claude API error rate | CloudWatch | > 5% over 5 min |
| Redis cache hit rate | CloudWatch | < 30% (investigate) |
| Token usage per day | CloudWatch | > $20/day |
| Prompt cache hit rate | Anthropic dashboard | < 50% |

### 4.2 Graceful Degradation

When Claude API is down or slow (> 10s):
- Search: Fall back to heuristic scoring (already works for free tier)
- Compare: Return apartments without analysis, show "AI analysis unavailable"
- Tour features: Show error toast, allow retry

### 4.3 Rate Limiting Anthropic Calls

Add a semaphore to limit concurrent Claude API calls to prevent runaway costs:

```python
_claude_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent Claude calls

async with _claude_semaphore:
    result = await asyncio.to_thread(self.claude_service.score_apartments, ...)
```

---

## Implementation Priority

| Priority | Task | Impact | Effort |
|----------|------|--------|--------|
| P0 | Haiku for search scoring | 75% latency reduction | 1 line change |
| P0 | Token usage logging | Cost visibility | 30 min |
| P1 | Parallel scoring batches | 40% latency for large results | 2 hours |
| P1 | Claude semaphore | Cost safety | 30 min |
| P2 | SSE streaming for compare | Perceived <1s latency | 1 day |
| P2 | Model tiering (4 methods) | 60% cost reduction | 1 hour |
| P3 | Scoring calibration | Quality improvement | Ongoing |
| P3 | Few-shot examples | Consistency | 2 hours |
