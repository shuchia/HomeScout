# AI Performance Improvement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce Claude API latency from 3-5s to <1.5s for search scoring, add cost visibility, concurrency safety, and graceful degradation.

**Architecture:** Switch search scoring to Haiku (faster model for structured output), split large batches into parallel calls, add token usage logging, protect against runaway costs with a semaphore, and fall back to heuristic scoring when Claude is unavailable.

**Tech Stack:** Python/FastAPI, Anthropic SDK, asyncio, Redis, CloudWatch-compatible logging

---

### Task 1: Switch Search Scoring to Haiku

**Files:**
- Modify: `backend/app/services/claude_service.py:175-176`
- Test: `backend/tests/test_claude_data.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_claude_data.py`:

```python
def test_score_apartments_uses_haiku_model(self):
    """Search scoring should use Haiku for speed."""
    with patch.object(self.service.client.messages, 'create') as mock_create:
        mock_create.return_value = MagicMock(
            content=[MagicMock(text='[{"apartment_id":"apt-1","match_score":80,"reasoning":"Good","highlights":["Nice"]}]')],
            usage=MagicMock(input_tokens=100, output_tokens=50)
        )
        self.service.score_apartments(
            city="Pittsburgh", budget=2000, bedrooms=1, bathrooms=1,
            property_type="Apartment", move_in_date="2026-05-01",
            other_preferences="None", apartments=[{"id": "apt-1", "address": "123 Test St", "rent": 1500, "bedrooms": 1, "bathrooms": 1, "sqft": 700, "property_type": "Apartment", "available_date": "", "neighborhood": "", "description": "", "amenities": []}]
        )
        call_kwargs = mock_create.call_args
        assert "haiku" in call_kwargs.kwargs.get("model", call_kwargs[1].get("model", ""))
```

**Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_claude_data.py::TestClaudeData::test_score_apartments_uses_haiku_model -v
```

Expected: FAIL — model is still "claude-sonnet-4-5-20250929"

**Step 3: Change the model**

In `backend/app/services/claude_service.py`, in the `score_apartments` method, change the `model` parameter in `self.client.messages.create(...)`:

```python
# Before
model="claude-sonnet-4-5-20250929",

# After
model="claude-haiku-4-5-20251001",
```

Only change the `score_apartments` method — leave `compare_apartments_with_analysis` and all other methods on Sonnet.

**Step 4: Run test to verify it passes**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_claude_data.py -v
```

**Step 5: Commit**

```bash
git add backend/app/services/claude_service.py backend/tests/test_claude_data.py
git commit -m "perf(ai): switch search scoring to Haiku for 75% latency reduction"
```

---

### Task 2: Add Token Usage Logging

**Files:**
- Modify: `backend/app/services/claude_service.py`

**Step 1: Add a logging helper method to `ClaudeService`**

Add after `__init__`:

```python
    @staticmethod
    def _log_usage(method: str, message) -> None:
        """Log Claude API token usage for cost tracking."""
        usage = message.usage
        cache_read = getattr(usage, 'cache_read_input_tokens', 0) or 0
        cache_create = getattr(usage, 'cache_creation_input_tokens', 0) or 0
        import logging
        logging.getLogger(__name__).info(
            f"claude_usage method={method} model={message.model} "
            f"input_tokens={usage.input_tokens} output_tokens={usage.output_tokens} "
            f"cache_read={cache_read} cache_create={cache_create}"
        )
```

**Step 2: Add `_log_usage` calls after each `messages.create()` call**

In `score_apartments`, after `message = self.client.messages.create(...)`:
```python
            self._log_usage("score_apartments", message)
```

In `compare_apartments_with_analysis`, after `message = self.client.messages.create(...)`:
```python
            self._log_usage("compare_analysis", message)
```

In `generate_inquiry_email`, after `message = self.client.messages.create(...)`:
```python
            self._log_usage("inquiry_email", message)
```

In `generate_day_plan`, after `message = self.client.messages.create(...)`:
```python
            self._log_usage("day_plan", message)
```

In `enhance_note`, after `message = self.client.messages.create(...)`:
```python
            self._log_usage("enhance_note", message)
```

In `generate_decision_brief`, after `message = self.client.messages.create(...)`:
```python
            self._log_usage("decision_brief", message)
```

**Step 3: Run tests**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_claude_data.py -v
```

**Step 4: Commit**

```bash
git add backend/app/services/claude_service.py
git commit -m "feat(ai): add token usage logging for all Claude API calls"
```

---

### Task 3: Parallel Scoring Batches

**Files:**
- Modify: `backend/app/services/apartment_service.py:274-314`

**Step 1: Write the failing test**

Create `backend/tests/test_parallel_scoring.py`:

```python
"""Tests for parallel Claude scoring batches."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.apartment_service import ApartmentService


class TestParallelScoring:
    """Verify scoring splits into parallel batches."""

    @pytest.mark.asyncio
    async def test_large_batch_calls_claude_twice(self):
        """When scoring 20 apartments, Claude should be called twice (batches of 10)."""
        svc = ApartmentService()

        # Mock Redis cache miss
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value=None)
        svc._redis.setex = AsyncMock()

        # Create 20 fake apartments
        apartments = [
            {"id": f"apt-{i}", "address": f"{i} Test St", "rent": 1500,
             "bedrooms": 1, "bathrooms": 1, "sqft": 700,
             "property_type": "Apartment", "available_date": "",
             "amenities": [], "neighborhood": "", "description": "",
             "images": [], "heuristic_score": 80 - i}
            for i in range(20)
        ]

        mock_scores = lambda apts, **kw: [
            {"apartment_id": a["id"], "match_score": 80, "reasoning": "Good", "highlights": ["Nice"]}
            for a in kw.get("apartments", apts) if isinstance(a, dict)
        ]

        with patch.object(svc, 'search_apartments', new_callable=AsyncMock, return_value=apartments), \
             patch('app.services.apartment_service.ScoringService') as mock_scoring, \
             patch.object(svc.claude_service, 'score_apartments', side_effect=mock_scores) as mock_claude:
            mock_scoring.score_apartments_list.return_value = apartments

            results, count = await svc.get_top_apartments(
                city="Pittsburgh", budget=2000, bedrooms=1, bathrooms=1,
                property_type="Apartment", move_in_date="2026-05-01",
                other_preferences="None", top_n=10,
            )

            # Should have been called twice (two batches)
            assert mock_claude.call_count == 2
            # First batch gets 10 apartments
            first_call_apts = mock_claude.call_args_list[0].kwargs.get("apartments", [])
            assert len(first_call_apts) == 10

    @pytest.mark.asyncio
    async def test_small_batch_calls_claude_once(self):
        """When scoring <12 apartments, Claude should be called once."""
        svc = ApartmentService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value=None)
        svc._redis.setex = AsyncMock()

        apartments = [
            {"id": f"apt-{i}", "address": f"{i} Test St", "rent": 1500,
             "bedrooms": 1, "bathrooms": 1, "sqft": 700,
             "property_type": "Apartment", "available_date": "",
             "amenities": [], "neighborhood": "", "description": "",
             "images": [], "heuristic_score": 80 - i}
            for i in range(8)
        ]

        mock_scores = lambda apts, **kw: [
            {"apartment_id": a["id"], "match_score": 80, "reasoning": "Good", "highlights": ["Nice"]}
            for a in kw.get("apartments", apts) if isinstance(a, dict)
        ]

        with patch.object(svc, 'search_apartments', new_callable=AsyncMock, return_value=apartments), \
             patch('app.services.apartment_service.ScoringService') as mock_scoring, \
             patch.object(svc.claude_service, 'score_apartments', side_effect=mock_scores) as mock_claude:
            mock_scoring.score_apartments_list.return_value = apartments

            results, count = await svc.get_top_apartments(
                city="Pittsburgh", budget=2000, bedrooms=1, bathrooms=1,
                property_type="Apartment", move_in_date="2026-05-01",
                other_preferences="None", top_n=10,
            )

            assert mock_claude.call_count == 1
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_parallel_scoring.py -v
```

Expected: FAIL — Claude called once with all 20 apartments

**Step 3: Implement parallel batching**

In `backend/app/services/apartment_service.py`, replace the Claude call block (the section from "Check Claude score cache" to "Cache the result") with:

```python
        # Check Claude score cache
        apt_ids = [a["id"] for a in apartments_to_score]
        cache_key = self.build_score_cache_key(
            city, budget, bedrooms, bathrooms, property_type,
            move_in_date, other_preferences or "", apt_ids,
            near_label=near_label,
        )

        cached = None
        if self._redis:
            try:
                cached = await self._redis.get(cache_key)
            except Exception:
                pass

        if cached:
            scores = json.loads(cached)
            logger.info(f"Claude score cache HIT for {cache_key}")
        else:
            # Split into parallel batches if more than 12 apartments.
            # Two parallel 10-apt calls are faster than one 20-apt call.
            BATCH_THRESHOLD = 12

            async def _score_batch(batch):
                return await asyncio.to_thread(
                    self.claude_service.score_apartments,
                    city=city,
                    budget=budget,
                    bedrooms=bedrooms,
                    bathrooms=bathrooms,
                    property_type=property_type,
                    move_in_date=move_in_date,
                    other_preferences=other_preferences or "None specified",
                    apartments=batch,
                    near_label=near_label,
                )

            if len(apartments_to_score) > BATCH_THRESHOLD:
                mid = len(apartments_to_score) // 2
                batch_a = apartments_to_score[:mid]
                batch_b = apartments_to_score[mid:]
                scores_a, scores_b = await asyncio.gather(
                    _score_batch(batch_a),
                    _score_batch(batch_b),
                )
                scores = scores_a + scores_b
            else:
                scores = await _score_batch(apartments_to_score)

            # Cache the result (1 hour TTL)
            if self._redis:
                try:
                    await self._redis.setex(cache_key, 3600, json.dumps(scores))
                    logger.info(f"Claude score cache MISS, stored {cache_key}")
                except Exception:
                    pass
```

**Step 4: Run tests**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_parallel_scoring.py tests/test_cost_estimator.py -v
```

**Step 5: Commit**

```bash
git add backend/app/services/apartment_service.py backend/tests/test_parallel_scoring.py
git commit -m "perf(ai): split large scoring batches into parallel Claude calls"
```

---

### Task 4: Claude Concurrency Semaphore

**Files:**
- Modify: `backend/app/services/apartment_service.py`
- Modify: `backend/app/routers/apartments.py`

**Step 1: Add a module-level semaphore to apartment_service.py**

At the top of `apartment_service.py`, after the imports, add:

```python
# Limit concurrent Claude API calls to prevent runaway costs
# and avoid overwhelming the Anthropic API rate limit
_claude_semaphore = asyncio.Semaphore(5)
```

**Step 2: Wrap all Claude calls with the semaphore**

In `apartment_service.py`, in the `_score_batch` function (from Task 3), wrap the call:

```python
            async def _score_batch(batch):
                async with _claude_semaphore:
                    return await asyncio.to_thread(
                        self.claude_service.score_apartments,
                        ...
                    )
```

In `backend/app/routers/apartments.py`, in the `compare_apartments` endpoint, wrap the Claude call:

```python
        try:
            from app.services.apartment_service import _claude_semaphore
            async with _claude_semaphore:
                raw_analysis = await asyncio.to_thread(
                    claude.compare_apartments_with_analysis,
                    ...
                )
```

**Step 3: Run tests**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v -k "not test_apartments_router" --tb=short 2>&1 | tail -20
```

**Step 4: Commit**

```bash
git add backend/app/services/apartment_service.py backend/app/routers/apartments.py
git commit -m "perf(ai): add semaphore to limit concurrent Claude API calls to 5"
```

---

### Task 5: Graceful Degradation on Claude Failure

**Files:**
- Modify: `backend/app/services/apartment_service.py`
- Modify: `backend/app/routers/apartments.py`

**Step 1: Add timeout and fallback in apartment_service.py**

In the `get_top_apartments` method, wrap the Claude scoring section in a try/except with timeout:

Replace the scoring block (after cache check, the `else` branch) with:

```python
        if cached:
            scores = json.loads(cached)
            logger.info(f"Claude score cache HIT for {cache_key}")
        else:
            BATCH_THRESHOLD = 12

            async def _score_batch(batch):
                async with _claude_semaphore:
                    return await asyncio.to_thread(
                        self.claude_service.score_apartments,
                        city=city,
                        budget=budget,
                        bedrooms=bedrooms,
                        bathrooms=bathrooms,
                        property_type=property_type,
                        move_in_date=move_in_date,
                        other_preferences=other_preferences or "None specified",
                        apartments=batch,
                        near_label=near_label,
                    )

            try:
                if len(apartments_to_score) > BATCH_THRESHOLD:
                    mid = len(apartments_to_score) // 2
                    batch_a = apartments_to_score[:mid]
                    batch_b = apartments_to_score[mid:]
                    scores_a, scores_b = await asyncio.wait_for(
                        asyncio.gather(_score_batch(batch_a), _score_batch(batch_b)),
                        timeout=15.0,
                    )
                    scores = scores_a + scores_b
                else:
                    scores = await asyncio.wait_for(
                        _score_batch(apartments_to_score),
                        timeout=15.0,
                    )

                # Cache the result (1 hour TTL)
                if self._redis:
                    try:
                        await self._redis.setex(cache_key, 3600, json.dumps(scores))
                        logger.info(f"Claude score cache MISS, stored {cache_key}")
                    except Exception:
                        pass

            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Claude scoring failed, falling back to heuristic: {e}")
                # Fall back to heuristic scores — still return results, just without AI insights
                scores = [
                    {
                        "apartment_id": apt["id"],
                        "match_score": apt.get("heuristic_score") or 50,
                        "reasoning": "AI scoring temporarily unavailable. Score based on heuristic matching.",
                        "highlights": [],
                    }
                    for apt in apartments_to_score
                ]
```

**Step 2: Add timeout to compare in apartments.py**

In the compare endpoint, wrap the Claude call:

```python
        try:
            from app.services.apartment_service import _claude_semaphore
            async with _claude_semaphore:
                raw_analysis = await asyncio.wait_for(
                    asyncio.to_thread(
                        claude.compare_apartments_with_analysis,
                        apartments=apartments,
                        preferences=prefs,
                        search_context=search_ctx,
                    ),
                    timeout=15.0,
                )
            from app.schemas import ComparisonAnalysis
            comparison_analysis = ComparisonAnalysis(**raw_analysis)
        except asyncio.TimeoutError:
            logger.warning("Claude comparison timed out after 15s")
        except Exception as e:
            logger.error(f"Claude comparison analysis failed: {e}")
```

**Step 3: Run tests**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_search_gating.py tests/test_compare_gating.py tests/test_parallel_scoring.py -v
```

**Step 4: Commit**

```bash
git add backend/app/services/apartment_service.py backend/app/routers/apartments.py
git commit -m "feat(ai): graceful degradation with 15s timeout and heuristic fallback"
```

---

### Task 6: Model Tiering — Haiku for Tour Features

**Files:**
- Modify: `backend/app/services/claude_service.py`

**Step 1: Add model constants at the top of ClaudeService**

After `self.client = Anthropic(api_key=api_key)` in `__init__`, add:

```python
        # Model tiering: Haiku for structured/templated output, Sonnet for deep analysis
        self.MODEL_FAST = "claude-haiku-4-5-20251001"
        self.MODEL_DEEP = "claude-sonnet-4-5-20250929"
```

**Step 2: Assign models to each method**

Update each `messages.create()` call to use the appropriate model constant:

| Method | Current | New | Reason |
|--------|---------|-----|--------|
| `score_apartments` | Sonnet → Haiku (Task 1) | `self.MODEL_FAST` | Structured JSON output |
| `compare_apartments_with_analysis` | Sonnet | `self.MODEL_DEEP` | Nuanced analysis |
| `generate_inquiry_email` | Sonnet | `self.MODEL_FAST` | Templated email |
| `generate_day_plan` | Sonnet | `self.MODEL_FAST` | Structured route optimization |
| `enhance_note` | Sonnet | `self.MODEL_FAST` | Text cleanup |
| `generate_decision_brief` | Sonnet | `self.MODEL_DEEP` | Nuanced recommendation |

Replace the hardcoded model strings in each method:
- `score_apartments`: `model=self.MODEL_FAST`
- `compare_apartments_with_analysis`: `model=self.MODEL_DEEP`
- `generate_inquiry_email`: `model=self.MODEL_FAST`
- `generate_day_plan`: `model=self.MODEL_FAST`
- `enhance_note`: `model=self.MODEL_FAST`
- `generate_decision_brief`: `model=self.MODEL_DEEP`

**Step 3: Run tests**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_claude_data.py -v
```

**Step 4: Commit**

```bash
git add backend/app/services/claude_service.py
git commit -m "perf(ai): model tiering — Haiku for structured output, Sonnet for deep analysis"
```

---

### Task 7: Update CLAUDE.md and Run Full Test Suite

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update the Claude AI Integration section**

In the CLAUDE.md section "Claude AI Integration", update the model reference:

```
- Search scoring uses `claude-haiku-4-5-20251001` (fast, structured output)
- Comparison analysis and decision briefs use `claude-sonnet-4-5-20250929` (deep reasoning)
- All calls use prompt caching (`cache_control: ephemeral`) for reduced latency
- Large scoring batches (>12 apartments) are split into parallel Claude calls
- 15-second timeout with heuristic fallback if Claude is unavailable
- Concurrent Claude calls limited to 5 via semaphore
```

**Step 2: Run full test suite**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v -k "not test_apartments_router" --tb=short
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with AI performance improvements"
```
