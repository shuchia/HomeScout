# Continuous Scraping Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the production-grade continuous scraping pipeline with database-driven market configs, tiered freshness, confidence-based invalidation, and resilient error handling.

**Architecture:** Enhanced Celery Pipeline — dispatcher pattern reads `MarketConfig` table hourly, spawns per-city scrape tasks, confidence scores decay per market tier, active verification at threshold.

**Tech Stack:** Python 3.11+, Celery + Redis, Apify (apartments.com), PostgreSQL + async SQLAlchemy, Alembic, FastAPI, Next.js + TypeScript

**Design doc:** `docs/plans/2026-02-19-continuous-scraping-design.md`

---

### Task 1: MarketConfig ORM Model

**Files:**
- Create: `backend/app/models/market_config.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: Create the MarketConfig model**

Create `backend/app/models/market_config.py`:

```python
"""
SQLAlchemy ORM model for market configuration.
Drives the scraping schedule — one row per city/market.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base


class MarketConfigModel(Base):
    """
    Configuration for a scraping market (city).
    The dispatcher queries this table hourly to decide what to scrape.
    """
    __tablename__ = "market_configs"

    id = Column(String(50), primary_key=True)  # e.g. "nyc", "philadelphia"
    display_name = Column(String(200), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(10), nullable=False)
    tier = Column(String(20), nullable=False, default="cool")  # hot, standard, cool
    is_enabled = Column(Boolean, nullable=False, default=True)
    max_listings_per_scrape = Column(Integer, nullable=False, default=100)
    scrape_frequency_hours = Column(Integer, nullable=False, default=24)
    last_scrape_at = Column(DateTime(timezone=True), nullable=True)
    last_scrape_status = Column(String(20), nullable=True)  # completed, failed, partial
    consecutive_failures = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Decay rate per hour for freshness confidence
    @property
    def decay_rate(self) -> int:
        """Confidence points lost per hour based on tier."""
        rates = {"hot": 3, "standard": 2, "cool": 1}
        return rates.get(self.tier, 1)

    def __repr__(self):
        return f"<Market {self.id}: {self.display_name} ({self.tier})>"
```

**Step 2: Update models __init__.py**

Add to `backend/app/models/__init__.py`:

```python
"""
ORM models for HomeScout database.
"""
from app.models.apartment import ApartmentModel
from app.models.scrape_job import ScrapeJobModel
from app.models.data_source import DataSourceModel
from app.models.market_config import MarketConfigModel

__all__ = ["ApartmentModel", "ScrapeJobModel", "DataSourceModel", "MarketConfigModel"]
```

**Step 3: Commit**

```bash
git add backend/app/models/market_config.py backend/app/models/__init__.py
git commit -m "feat: add MarketConfig ORM model for database-driven scheduling"
```

---

### Task 2: Add Freshness Columns to ApartmentModel

**Files:**
- Modify: `backend/app/models/apartment.py`

**Step 1: Add new columns and indexes**

Add these columns after line 64 (`is_active` column) in `backend/app/models/apartment.py`:

```python
    # Freshness tracking
    freshness_confidence = Column(Integer, nullable=False, default=100)  # 0-100
    confidence_updated_at = Column(DateTime(timezone=True), nullable=True)
    verification_status = Column(String(20), nullable=True)  # null, pending, verified, gone
    verified_at = Column(DateTime(timezone=True), nullable=True)
    times_seen = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    market_id = Column(String(50), nullable=True)  # FK to market_configs.id
```

Add these indexes to the `__table_args__` tuple (before the closing parenthesis):

```python
        Index('idx_apartments_freshness', 'freshness_confidence'),
        Index('idx_apartments_verification', 'verification_status'),
        Index('idx_apartments_market', 'market_id'),
```

**Step 2: Update to_dict() to expose new fields**

Add these fields to the `to_dict()` return dict in `backend/app/models/apartment.py`, after `"data_quality_score"`:

```python
            "freshness_confidence": self.freshness_confidence,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "times_seen": self.times_seen,
```

**Step 3: Commit**

```bash
git add backend/app/models/apartment.py
git commit -m "feat: add freshness confidence and verification columns to ApartmentModel"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/002_continuous_scraping.py`

**Step 1: Generate and edit the migration**

Run from `backend/` directory:

```bash
cd backend
source .venv/bin/activate
alembic revision -m "add market configs and freshness tracking"
```

Then edit the generated file to contain:

```python
"""add market configs and freshness tracking

Revision ID: 002
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create market_configs table
    op.create_table(
        'market_configs',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('state', sa.String(10), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False, server_default='cool'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('max_listings_per_scrape', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('scrape_frequency_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('last_scrape_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_scrape_status', sa.String(20), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add freshness columns to apartments
    op.add_column('apartments', sa.Column('freshness_confidence', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('apartments', sa.Column('confidence_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('apartments', sa.Column('verification_status', sa.String(20), nullable=True))
    op.add_column('apartments', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('apartments', sa.Column('times_seen', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('apartments', sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column('apartments', sa.Column('market_id', sa.String(50), nullable=True))

    # Add indexes
    op.create_index('idx_apartments_freshness', 'apartments', ['freshness_confidence'])
    op.create_index('idx_apartments_verification', 'apartments', ['verification_status'])
    op.create_index('idx_apartments_market', 'apartments', ['market_id'])

    # Truncate apartments (fresh start)
    op.execute("TRUNCATE TABLE apartments")

    # Seed market_configs with East Coast markets
    op.execute("""
        INSERT INTO market_configs (id, display_name, city, state, tier, scrape_frequency_hours) VALUES
        ('philadelphia', 'Philadelphia', 'Philadelphia', 'PA', 'hot', 6),
        ('nyc', 'New York City', 'New York', 'NY', 'hot', 6),
        ('boston', 'Boston', 'Boston', 'MA', 'hot', 6),
        ('washington-dc', 'Washington DC', 'Washington', 'DC', 'hot', 6),
        ('pittsburgh', 'Pittsburgh', 'Pittsburgh', 'PA', 'standard', 12),
        ('baltimore', 'Baltimore', 'Baltimore', 'MD', 'standard', 12),
        ('newark', 'Newark', 'Newark', 'NJ', 'standard', 12),
        ('jersey-city', 'Jersey City', 'Jersey City', 'NJ', 'standard', 12),
        ('cambridge', 'Cambridge', 'Cambridge', 'MA', 'standard', 12),
        ('arlington-va', 'Arlington VA', 'Arlington', 'VA', 'standard', 12),
        ('bryn-mawr', 'Bryn Mawr', 'Bryn Mawr', 'PA', 'cool', 24),
        ('hoboken', 'Hoboken', 'Hoboken', 'NJ', 'cool', 24),
        ('stamford', 'Stamford', 'Stamford', 'CT', 'cool', 24),
        ('new-haven', 'New Haven', 'New Haven', 'CT', 'cool', 24),
        ('providence', 'Providence', 'Providence', 'RI', 'cool', 24),
        ('richmond', 'Richmond', 'Richmond', 'VA', 'cool', 24),
        ('charlotte', 'Charlotte', 'Charlotte', 'NC', 'cool', 24),
        ('raleigh', 'Raleigh', 'Raleigh', 'NC', 'cool', 24),
        ('hartford', 'Hartford', 'Hartford', 'CT', 'cool', 24)
    """)


def downgrade() -> None:
    op.drop_index('idx_apartments_market', 'apartments')
    op.drop_index('idx_apartments_verification', 'apartments')
    op.drop_index('idx_apartments_freshness', 'apartments')
    op.drop_column('apartments', 'market_id')
    op.drop_column('apartments', 'first_seen_at')
    op.drop_column('apartments', 'times_seen')
    op.drop_column('apartments', 'verified_at')
    op.drop_column('apartments', 'verification_status')
    op.drop_column('apartments', 'confidence_updated_at')
    op.drop_column('apartments', 'freshness_confidence')
    op.drop_table('market_configs')
```

**Step 2: Run the migration**

```bash
alembic upgrade head
```

Expected: Migration applies successfully. `market_configs` has 19 rows. `apartments` is empty.

**Step 3: Verify**

```bash
psql homescout -c "SELECT count(*) FROM market_configs;"
# Expected: 19

psql homescout -c "SELECT id, tier, scrape_frequency_hours FROM market_configs ORDER BY tier, id;"
# Expected: 4 hot, 6 standard, 9 cool markets
```

**Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: migration for market_configs table and freshness columns"
```

---

### Task 4: Dispatcher Task

**Files:**
- Create: `backend/app/tasks/dispatcher.py`
- Modify: `backend/app/celery_app.py`

**Step 1: Create the dispatcher task**

Create `backend/app/tasks/dispatcher.py`:

```python
"""
Dispatcher task — runs hourly, checks which markets need scraping,
and spawns individual scrape_city_task for each.
"""
import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from app.celery_app import celery_app
from app.database import get_session_context, is_database_enabled

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine in a sync context."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task
def dispatch_scrapes() -> Dict[str, Any]:
    """
    Hourly dispatcher: check market_configs, spawn scrape tasks for markets that are due.

    Skips markets that:
    - are disabled
    - were scraped recently (within scrape_frequency_hours)
    - have 3+ consecutive failures (circuit breaker)
    - already have a running scrape job
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_dispatch())


async def _dispatch() -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.market_config import MarketConfigModel
    from app.models.scrape_job import ScrapeJobModel

    now = datetime.now(timezone.utc)
    dispatched = []
    skipped = []

    async with get_session_context() as session:
        # Get all enabled markets
        stmt = select(MarketConfigModel).where(MarketConfigModel.is_enabled == True)
        result = await session.execute(stmt)
        markets = list(result.scalars())

        # Get currently running jobs
        running_stmt = select(ScrapeJobModel.city).where(ScrapeJobModel.status == "running")
        running_result = await session.execute(running_stmt)
        running_cities = {row[0] for row in running_result}

        for market in markets:
            # Circuit breaker: skip after 3 consecutive failures
            if market.consecutive_failures >= 3:
                skipped.append({"market": market.id, "reason": "circuit_breaker"})
                continue

            # Check if scrape is due
            if market.last_scrape_at:
                from datetime import timedelta
                next_scrape = market.last_scrape_at + timedelta(hours=market.scrape_frequency_hours)
                if now < next_scrape:
                    skipped.append({"market": market.id, "reason": "not_due"})
                    continue

            # Check if already running
            if market.city in running_cities:
                skipped.append({"market": market.id, "reason": "already_running"})
                continue

            # Dispatch with random stagger (0-60s)
            delay = random.randint(0, 60)
            from app.tasks.scrape_tasks import scrape_city_task
            scrape_city_task.apply_async(
                kwargs={"market_id": market.id},
                countdown=delay,
                queue="scraping",
            )
            dispatched.append({"market": market.id, "delay_seconds": delay})

    logger.info(f"Dispatched {len(dispatched)} scrapes, skipped {len(skipped)}")
    return {
        "status": "completed",
        "dispatched": dispatched,
        "skipped": skipped,
        "timestamp": now.isoformat(),
    }
```

**Step 2: Update Celery beat schedule**

Replace the entire `celery_app.conf.beat_schedule` block in `backend/app/celery_app.py` with:

```python
# Beat schedule — 3 orchestrator tasks only
celery_app.conf.beat_schedule = {
    # Dispatcher: check which markets need scraping
    "dispatch-scrapes": {
        "task": "app.tasks.dispatcher.dispatch_scrapes",
        "schedule": crontab(minute=0),  # Every hour at :00
    },

    # Decay confidence scores and trigger verification
    "decay-and-verify": {
        "task": "app.tasks.maintenance_tasks.decay_and_verify",
        "schedule": crontab(minute=30),  # Every hour at :30
    },

    # Daily maintenance at 3 AM UTC
    "cleanup-maintenance": {
        "task": "app.tasks.maintenance_tasks.cleanup_maintenance",
        "schedule": crontab(hour=3, minute=0),
    },
}
```

Also add `"app.tasks.dispatcher"` to the `include` list in the Celery app creation (line 21-24):

```python
    include=[
        "app.tasks.scrape_tasks",
        "app.tasks.maintenance_tasks",
        "app.tasks.dispatcher",
    ]
```

**Step 3: Commit**

```bash
git add backend/app/tasks/dispatcher.py backend/app/celery_app.py
git commit -m "feat: add dispatch_scrapes task and update beat schedule"
```

---

### Task 5: Rewrite scrape_city_task for Market-Driven Scraping

**Files:**
- Modify: `backend/app/tasks/scrape_tasks.py`

**Step 1: Rewrite scrape_city_task to accept market_id**

Replace the existing `scrape_city_task` function (lines 308-353) in `backend/app/tasks/scrape_tasks.py` with:

```python
@celery_app.task(bind=True, max_retries=3)
def scrape_city_task(self, market_id: str) -> Dict[str, Any]:
    """
    Scrape a single market. Called by the dispatcher.

    Args:
        market_id: ID from market_configs table

    Returns:
        Dict with scrape results
    """
    logger.info(f"Starting scrape for market: {market_id}")
    return run_async(_scrape_market(self, market_id))


async def _scrape_market(task, market_id: str) -> Dict[str, Any]:
    """Async implementation of market scraping."""
    from sqlalchemy import select, update
    from app.models.market_config import MarketConfigModel
    from app.models.scrape_job import ScrapeJobModel

    # Load market config
    async with get_session_context() as session:
        result = await session.execute(
            select(MarketConfigModel).where(MarketConfigModel.id == market_id)
        )
        market = result.scalar_one_or_none()
        if not market:
            return {"status": "failed", "error": f"Market {market_id} not found"}

        city = market.city
        state = market.state
        max_listings = market.max_listings_per_scrape

    # Create scrape job record
    job_id = str(uuid.uuid4())
    async with get_session_context() as session:
        job = ScrapeJobModel(
            id=job_id,
            source="apartments_com",
            job_type="scheduled",
            status="running",
            city=city,
            state=state,
            started_at=datetime.utcnow(),
        )
        session.add(job)
        await session.commit()

    # Check rate limits
    from app.models.data_source import DataSourceModel
    async with get_session_context() as session:
        ds_result = await session.execute(
            select(DataSourceModel).where(DataSourceModel.name == "apartments_com")
        )
        data_source = ds_result.scalar_one_or_none()
        if data_source and not data_source.can_make_request():
            logger.warning(f"Rate limit exceeded for apartments_com, skipping {market_id}")
            await _update_job(job_id, "failed", error="Rate limit exceeded")
            return {"status": "skipped", "reason": "rate_limit"}

    # Run the scrape
    normalizer = NormalizationService()
    deduplicator = DeduplicationService()
    scraper = ApifyService("apartments_com")

    try:
        scrape_result = await scraper.scrape(
            city=city, state=state, max_listings=max_listings
        )

        found = len(scrape_result.listings)

        # Normalize
        normalized = []
        errors = 0
        for listing in scrape_result.listings:
            norm_result = normalizer.normalize(listing)
            if norm_result.success:
                norm_result.listing["id"] = str(uuid.uuid4())
                norm_result.listing["data_quality_score"] = norm_result.quality_score
                norm_result.listing["market_id"] = market_id
                normalized.append(norm_result.listing)
            else:
                errors += 1
                logger.warning(f"Normalization failed: {norm_result.errors}")

        # Deduplicate with re-see updates
        new_count = 0
        updated_count = 0
        dup_count = 0

        if normalized:
            existing_hashes, existing_listings = await _get_existing_data(city)

            new_listings, updates, dups = deduplicator.deduplicate_batch_with_updates(
                normalized, existing_hashes, existing_listings
            )

            new_count = len(new_listings)
            updated_count = len(updates)
            dup_count = len(dups)

            # Save new listings
            if new_listings:
                await _save_listings(new_listings, job_id)

            # Update re-seen listings (confidence reset)
            if updates:
                await _update_reseen_listings(updates)

        # Update job and market
        await _update_job(job_id, "completed",
            listings_found=found, listings_new=new_count,
            listings_updated=updated_count, listings_duplicates=dup_count,
            listings_errors=errors)

        await _update_market_after_scrape(market_id, "completed")

        result = {
            "status": "completed",
            "market_id": market_id,
            "city": city,
            "found": found,
            "new": new_count,
            "updated": updated_count,
            "duplicates": dup_count,
            "errors": errors,
        }
        logger.info(f"Scrape {market_id}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Scrape failed for {market_id}: {e}")
        await _update_job(job_id, "failed", error=str(e))
        await _update_market_after_scrape(market_id, "failed")

        if task.request.retries < task.max_retries:
            raise task.retry(exc=e, countdown=60 * (task.request.retries + 1))

        return {"status": "failed", "market_id": market_id, "error": str(e)}

    finally:
        await scraper.close()
```

**Step 2: Add helper functions for job/market updates**

Add these at the end of `backend/app/tasks/scrape_tasks.py`:

```python
async def _update_job(job_id: str, status: str, **metrics):
    """Update a scrape job record."""
    from sqlalchemy import update
    from app.models.scrape_job import ScrapeJobModel

    values = {"status": status, "completed_at": datetime.utcnow()}
    values.update(metrics)

    async with get_session_context() as session:
        await session.execute(
            update(ScrapeJobModel).where(ScrapeJobModel.id == job_id).values(**values)
        )
        await session.commit()


async def _update_market_after_scrape(market_id: str, status: str):
    """Update market config after a scrape completes or fails."""
    from sqlalchemy import update
    from app.models.market_config import MarketConfigModel

    values = {
        "last_scrape_at": datetime.now(timezone.utc) if hasattr(datetime, 'now') else datetime.utcnow(),
        "last_scrape_status": status,
    }

    if status == "completed":
        values["consecutive_failures"] = 0
    else:
        from sqlalchemy import text
        async with get_session_context() as session:
            await session.execute(
                update(MarketConfigModel)
                .where(MarketConfigModel.id == market_id)
                .values(
                    last_scrape_at=datetime.utcnow(),
                    last_scrape_status=status,
                    consecutive_failures=MarketConfigModel.consecutive_failures + 1,
                )
            )
            await session.commit()
            return

    async with get_session_context() as session:
        await session.execute(
            update(MarketConfigModel).where(MarketConfigModel.id == market_id).values(**values)
        )
        await session.commit()


async def _update_reseen_listings(updates: List[Dict[str, Any]]):
    """Update existing listings that were re-seen in a scrape."""
    from sqlalchemy import update
    from app.models.apartment import ApartmentModel

    async with get_session_context() as session:
        for upd in updates:
            values = {
                "last_seen_at": datetime.utcnow(),
                "freshness_confidence": 100,
                "times_seen": ApartmentModel.times_seen + 1,
            }
            # Merge richer data if available
            if upd.get("images"):
                values["images"] = upd["images"]
            if upd.get("description") and len(upd.get("description", "")) > 100:
                values["description"] = upd["description"]

            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.id == upd["matched_id"])
                .values(**values)
            )
        await session.commit()
        logger.info(f"Updated {len(updates)} re-seen listings")
```

Also add this import at the top of the file:

```python
from datetime import datetime, timezone
```

**Step 3: Commit**

```bash
git add backend/app/tasks/scrape_tasks.py
git commit -m "feat: rewrite scrape_city_task for market-driven scraping with re-see updates"
```

---

### Task 6: Update DeduplicationService for Re-See Updates

**Files:**
- Modify: `backend/app/services/deduplication/deduplicator.py`

**Step 1: Add deduplicate_batch_with_updates method**

Add this new method to the `DeduplicationService` class in `backend/app/services/deduplication/deduplicator.py`:

```python
    def deduplicate_batch_with_updates(
        self,
        listings: List[Dict[str, Any]],
        existing_hashes: Dict[str, str],
        existing_listings: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Deduplicate a batch, returning new listings, updates for re-seen, and skipped duplicates.

        Unlike deduplicate_batch(), this separates duplicates into:
        - updates: re-seen listings that should have their confidence reset
        - skipped: true duplicates within the same batch

        Args:
            listings: New listings to check
            existing_hashes: Map of content_hash -> listing_id from DB
            existing_listings: Existing listings for fuzzy matching

        Returns:
            Tuple of (new_listings, updates_to_existing, skipped_duplicates)
        """
        new_listings = []
        updates = []
        skipped = []
        batch_hashes = {}  # Track hashes within this batch

        for listing in listings:
            content_hash = self.generate_content_hash(listing)
            listing["content_hash"] = content_hash

            # Check against existing DB data
            if content_hash in existing_hashes:
                updates.append({
                    "matched_id": existing_hashes[content_hash],
                    "content_hash": content_hash,
                    "images": listing.get("images", []),
                    "description": listing.get("description", ""),
                })
                continue

            # Check fuzzy match against existing
            if existing_listings:
                dup_result = self.check_duplicate(listing, existing_hashes, existing_listings)
                if dup_result.is_duplicate and dup_result.matched_id:
                    updates.append({
                        "matched_id": dup_result.matched_id,
                        "content_hash": content_hash,
                        "images": listing.get("images", []),
                        "description": listing.get("description", ""),
                    })
                    continue

            # Check within this batch
            if content_hash in batch_hashes:
                skipped.append(listing)
                continue

            batch_hashes[content_hash] = True
            new_listings.append(listing)

        logger.info(
            f"Dedup batch: {len(listings)} input → "
            f"{len(new_listings)} new, {len(updates)} re-seen, {len(skipped)} skipped"
        )
        return new_listings, updates, skipped
```

**Step 2: Commit**

```bash
git add backend/app/services/deduplication/deduplicator.py
git commit -m "feat: add deduplicate_batch_with_updates for re-see tracking"
```

---

### Task 7: Decay and Verify Tasks

**Files:**
- Modify: `backend/app/tasks/maintenance_tasks.py`

**Step 1: Add decay_and_verify task**

Add this task to `backend/app/tasks/maintenance_tasks.py`:

```python
@celery_app.task
def decay_and_verify() -> Dict[str, Any]:
    """
    Hourly task: recalculate freshness confidence and trigger verification
    for listings that have decayed below threshold.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_decay_and_verify())


async def _decay_and_verify() -> Dict[str, Any]:
    from sqlalchemy import select, update
    from app.models.apartment import ApartmentModel
    from app.models.market_config import MarketConfigModel

    now = datetime.utcnow()
    decay_counts = {"hot": 0, "standard": 0, "cool": 0}
    verification_dispatched = 0
    deactivated = 0

    async with get_session_context() as session:
        # Load all market configs for decay rates
        markets_result = await session.execute(select(MarketConfigModel))
        markets = {m.id: m for m in markets_result.scalars()}

        # Default decay rates by tier
        tier_rates = {"hot": 3, "standard": 2, "cool": 1}

        # Get all active listings
        stmt = select(ApartmentModel).where(ApartmentModel.is_active == 1)
        result = await session.execute(stmt)

        for apt in result.scalars():
            if not apt.last_seen_at:
                continue

            # Get decay rate from market or default
            market = markets.get(apt.market_id)
            tier = market.tier if market else "cool"
            decay_rate = tier_rates.get(tier, 1)

            # Calculate new confidence
            hours_since_seen = (now - apt.last_seen_at.replace(tzinfo=None)).total_seconds() / 3600
            new_confidence = max(0, int(100 - (hours_since_seen * decay_rate)))

            if new_confidence != apt.freshness_confidence:
                apt.freshness_confidence = new_confidence
                apt.confidence_updated_at = now
                decay_counts[tier] = decay_counts.get(tier, 0) + 1

            # Trigger verification at threshold
            if new_confidence < 40 and apt.verification_status is None:
                apt.verification_status = "pending"
                from app.tasks.maintenance_tasks import verify_listing
                verify_listing.apply_async(
                    kwargs={"apartment_id": apt.id},
                    queue="maintenance",
                )
                verification_dispatched += 1

            # Deactivate at zero confidence (unless verified)
            if new_confidence == 0 and apt.verification_status != "verified":
                apt.is_active = 0
                deactivated += 1

        await session.commit()

    logger.info(
        f"Decay update: {sum(decay_counts.values())} listings updated, "
        f"{verification_dispatched} verifications dispatched, "
        f"{deactivated} deactivated"
    )
    return {
        "status": "completed",
        "decay_counts": decay_counts,
        "verifications_dispatched": verification_dispatched,
        "deactivated": deactivated,
    }
```

**Step 2: Add verify_listing task**

Add this task to `backend/app/tasks/maintenance_tasks.py`:

```python
@celery_app.task
def verify_listing(apartment_id: str) -> Dict[str, Any]:
    """
    Verify if a listing is still active by checking its source URL.
    """
    if not is_database_enabled():
        return {"status": "skipped"}

    return run_async(_verify_listing(apartment_id))


async def _verify_listing(apartment_id: str) -> Dict[str, Any]:
    import httpx
    from sqlalchemy import select, update
    from app.models.apartment import ApartmentModel

    async with get_session_context() as session:
        result = await session.execute(
            select(ApartmentModel).where(ApartmentModel.id == apartment_id)
        )
        apt = result.scalar_one_or_none()
        if not apt or not apt.source_url:
            return {"status": "skipped", "reason": "no source_url"}

        source_url = apt.source_url

    # Check the URL
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(source_url)

        gone_indicators = [
            "no longer available",
            "this listing has been removed",
            "listing not found",
            "page not found",
        ]

        is_gone = response.status_code == 404
        if not is_gone and response.status_code == 200:
            body = response.text.lower()
            is_gone = any(indicator in body for indicator in gone_indicators)

        async with get_session_context() as session:
            now = datetime.utcnow()
            if is_gone:
                await session.execute(
                    update(ApartmentModel)
                    .where(ApartmentModel.id == apartment_id)
                    .values(verification_status="gone", verified_at=now, is_active=0)
                )
                status = "gone"
            else:
                await session.execute(
                    update(ApartmentModel)
                    .where(ApartmentModel.id == apartment_id)
                    .values(verification_status="verified", verified_at=now, freshness_confidence=80)
                )
                status = "verified"
            await session.commit()

        return {"status": status, "apartment_id": apartment_id}

    except Exception as e:
        logger.warning(f"Verification failed for {apartment_id}: {e}")
        return {"status": "pending", "error": str(e)}
```

**Step 3: Add cleanup_maintenance task**

Add this combined daily maintenance task to `backend/app/tasks/maintenance_tasks.py`:

```python
@celery_app.task
def cleanup_maintenance() -> Dict[str, Any]:
    """
    Daily maintenance: deactivate dead listings, reset circuit breakers,
    detect stale jobs, reset rate limits.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_cleanup_maintenance())


async def _cleanup_maintenance() -> Dict[str, Any]:
    from sqlalchemy import update
    from app.models.apartment import ApartmentModel
    from app.models.market_config import MarketConfigModel
    from app.models.scrape_job import ScrapeJobModel

    now = datetime.utcnow()
    results = {}

    async with get_session_context() as session:
        # 1. Deactivate listings with confidence=0 and not verified
        stmt = (
            update(ApartmentModel)
            .where(
                ApartmentModel.freshness_confidence == 0,
                ApartmentModel.is_active == 1,
                ApartmentModel.verification_status != "verified",
            )
            .values(is_active=0)
        )
        result = await session.execute(stmt)
        results["deactivated"] = result.rowcount

        # 2. Reset circuit breakers (consecutive_failures → 0)
        stmt = (
            update(MarketConfigModel)
            .where(MarketConfigModel.consecutive_failures > 0)
            .values(consecutive_failures=0)
        )
        result = await session.execute(stmt)
        results["circuit_breakers_reset"] = result.rowcount

        # 3. Detect stale jobs (running > 30 min)
        stale_cutoff = now - timedelta(minutes=30)
        stmt = (
            update(ScrapeJobModel)
            .where(
                ScrapeJobModel.status == "running",
                ScrapeJobModel.started_at < stale_cutoff,
            )
            .values(status="failed", completed_at=now)
        )
        result = await session.execute(stmt)
        results["stale_jobs_failed"] = result.rowcount

        await session.commit()

    # 4. Reset daily rate limits (reuse existing task logic)
    reset_result = reset_rate_limits(period="day")
    results["rate_limits_reset"] = reset_result

    logger.info(f"Daily maintenance: {results}")
    return {"status": "completed", **results}
```

Add this import at the top of the file if not present:

```python
from datetime import datetime, timedelta
```

**Step 4: Commit**

```bash
git add backend/app/tasks/maintenance_tasks.py
git commit -m "feat: add decay_and_verify, verify_listing, and cleanup_maintenance tasks"
```

---

### Task 8: Admin Market Endpoints

**Files:**
- Modify: `backend/app/routers/data_collection.py`
- Modify: `backend/app/main.py`

**Step 1: Add market admin endpoints**

Add these endpoints to the end of `backend/app/routers/data_collection.py`:

```python
# --- Market Configuration Endpoints ---

@router.get("/markets")
async def list_markets():
    """List all market configurations."""
    if not is_database_enabled():
        return {"markets": [], "message": "Database not enabled"}

    from sqlalchemy import select
    from app.models.market_config import MarketConfigModel

    async with get_session_context() as session:
        result = await session.execute(
            select(MarketConfigModel).order_by(MarketConfigModel.tier, MarketConfigModel.display_name)
        )
        markets = []
        for m in result.scalars():
            markets.append({
                "id": m.id,
                "display_name": m.display_name,
                "city": m.city,
                "state": m.state,
                "tier": m.tier,
                "is_enabled": m.is_enabled,
                "scrape_frequency_hours": m.scrape_frequency_hours,
                "max_listings_per_scrape": m.max_listings_per_scrape,
                "last_scrape_at": m.last_scrape_at.isoformat() if m.last_scrape_at else None,
                "last_scrape_status": m.last_scrape_status,
                "consecutive_failures": m.consecutive_failures,
            })
        return {"markets": markets, "total": len(markets)}


@router.post("/markets")
async def create_market(market: dict = Body(...)):
    """Add a new market. Required: id, display_name, city, state. Optional: tier, scrape_frequency_hours."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.models.market_config import MarketConfigModel

    async with get_session_context() as session:
        m = MarketConfigModel(
            id=market["id"],
            display_name=market["display_name"],
            city=market["city"],
            state=market["state"],
            tier=market.get("tier", "cool"),
            scrape_frequency_hours=market.get("scrape_frequency_hours", 24),
            max_listings_per_scrape=market.get("max_listings_per_scrape", 100),
        )
        session.add(m)
        await session.commit()
        return {"status": "created", "market_id": m.id}


@router.put("/markets/{market_id}")
async def update_market(market_id: str, updates: dict = Body(...)):
    """Update market config. Supports: tier, is_enabled, scrape_frequency_hours, max_listings_per_scrape."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import update, select
    from app.models.market_config import MarketConfigModel

    allowed = {"tier", "is_enabled", "scrape_frequency_hours", "max_listings_per_scrape"}
    values = {k: v for k, v in updates.items() if k in allowed}

    if not values:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with get_session_context() as session:
        await session.execute(
            update(MarketConfigModel).where(MarketConfigModel.id == market_id).values(**values)
        )
        await session.commit()
        return {"status": "updated", "market_id": market_id, "updated_fields": list(values.keys())}


@router.post("/markets/{market_id}/scrape")
async def trigger_market_scrape(market_id: str):
    """Trigger an immediate scrape for a specific market."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import select
    from app.models.market_config import MarketConfigModel

    async with get_session_context() as session:
        result = await session.execute(
            select(MarketConfigModel).where(MarketConfigModel.id == market_id)
        )
        market = result.scalar_one_or_none()
        if not market:
            raise HTTPException(status_code=404, detail=f"Market {market_id} not found")

    from app.tasks.scrape_tasks import scrape_city_task
    task = scrape_city_task.apply_async(kwargs={"market_id": market_id}, queue="scraping")

    return {"status": "dispatched", "market_id": market_id, "task_id": task.id}
```

Add this import at the top of the file if not present:

```python
from fastapi import Body
```

**Step 2: Commit**

```bash
git add backend/app/routers/data_collection.py
git commit -m "feat: add admin market CRUD and trigger-scrape endpoints"
```

---

### Task 9: Add Freshness Filter to API Endpoints

**Files:**
- Modify: `backend/app/routers/apartments.py`
- Modify: `backend/app/main.py`

**Step 1: Add freshness filter to list endpoint**

In `backend/app/routers/apartments.py`, in the `_list_from_database` function, add `freshness_confidence >= 40` to the base conditions:

```python
conditions = [ApartmentModel.is_active == 1, ApartmentModel.freshness_confidence >= 40]
```

**Step 2: Add freshness filter to search endpoint**

In `backend/app/main.py`, in the `/api/search` endpoint, wherever the search filters apartments from the database, add the same confidence filter. If search uses `apartment_service.py`, the filter should be applied there.

For the JSON fallback mode, no change needed (JSON listings don't have freshness scores).

**Step 3: Commit**

```bash
git add backend/app/routers/apartments.py backend/app/main.py
git commit -m "feat: filter out low-confidence listings from search and list endpoints"
```

---

### Task 10: Frontend Freshness Badge

**Files:**
- Modify: `frontend/types/apartment.ts`
- Modify: `frontend/components/ApartmentCard.tsx`

**Step 1: Add freshness fields to TypeScript types**

Add these optional fields to the `Apartment` interface in `frontend/types/apartment.ts`:

```typescript
  freshness_confidence?: number;
  first_seen_at?: string;
  times_seen?: number;
```

**Step 2: Add freshness badge to ApartmentCard**

In `frontend/components/ApartmentCard.tsx`, add a freshness badge helper:

```typescript
const getFreshnessBadge = (confidence?: number): { text: string; color: string } | null => {
  if (confidence === undefined || confidence >= 80) return null;
  if (confidence >= 50) return { text: 'Listed recently', color: 'bg-yellow-100 text-yellow-800' };
  if (confidence >= 40) return { text: 'May no longer be available', color: 'bg-orange-100 text-orange-800' };
  return null;
};
```

Then add the badge to the card's content section (after the available date, before amenities):

```tsx
        {/* Freshness Badge */}
        {getFreshnessBadge(apartment.freshness_confidence) && (
          <span className={`inline-block px-2 py-1 text-xs rounded-full ${getFreshnessBadge(apartment.freshness_confidence)!.color}`}>
            {getFreshnessBadge(apartment.freshness_confidence)!.text}
          </span>
        )}
```

**Step 3: Commit**

```bash
git add frontend/types/apartment.ts frontend/components/ApartmentCard.tsx
git commit -m "feat: add freshness badge to apartment cards"
```

---

### Task 11: Update _save_listings for New Fields

**Files:**
- Modify: `backend/app/tasks/scrape_tasks.py`

**Step 1: Update _save_listings to include freshness fields**

In the `_save_listings` function in `backend/app/tasks/scrape_tasks.py`, add these fields to the `ApartmentModel` constructor:

```python
                    freshness_confidence=100,
                    times_seen=1,
                    first_seen_at=datetime.utcnow(),
                    market_id=listing_data.get("market_id"),
```

**Step 2: Commit**

```bash
git add backend/app/tasks/scrape_tasks.py
git commit -m "feat: save freshness and market fields for new listings"
```

---

### Task 12: Manual Integration Test

**Step 1: Verify migration ran**

```bash
cd backend && source .venv/bin/activate
psql homescout -c "SELECT id, tier, scrape_frequency_hours FROM market_configs ORDER BY tier;"
```

Expected: 19 markets (4 hot, 6 standard, 9 cool)

**Step 2: Test admin endpoints**

```bash
# List markets
curl -s http://localhost:8000/api/admin/data-collection/markets | python3 -m json.tool | head -30

# Trigger a scrape for bryn-mawr (small market, quick test)
curl -s -X POST http://localhost:8000/api/admin/data-collection/markets/bryn-mawr/scrape

# Check job status after ~2 min
curl -s http://localhost:8000/api/admin/data-collection/jobs | python3 -m json.tool | head -20
```

**Step 3: Verify listings have freshness fields**

```bash
curl -s "http://localhost:8000/api/apartments/list?limit=3" | python3 -m json.tool | grep -E "freshness_confidence|times_seen|first_seen"
```

Expected: `freshness_confidence: 100`, `times_seen: 1`, `first_seen_at: <timestamp>`

**Step 4: Test decay (manually set last_seen_at to old time)**

```bash
psql homescout -c "UPDATE apartments SET last_seen_at = NOW() - INTERVAL '25 hours' WHERE id = (SELECT id FROM apartments LIMIT 1);"

# Run decay task
curl -s -X POST http://localhost:8000/api/admin/data-collection/markets/bryn-mawr/scrape
# Or trigger decay directly via celery
```

**Step 5: Commit any test fixes**

```bash
git add -A && git commit -m "fix: integration test fixes for continuous scraping pipeline"
```

---

### Task 13: Update E2E Tests

**Files:**
- Modify: `frontend/e2e/homescout.spec.ts`

**Step 1: Update mock data to include freshness fields**

In `frontend/e2e/homescout.spec.ts`, update the `MOCK_SEARCH_RESPONSE` to include the new optional fields in apartment objects:

```typescript
      freshness_confidence: 100,
      first_seen_at: '2026-02-19T10:00:00Z',
      times_seen: 3,
```

**Step 2: Run E2E tests**

```bash
cd frontend && npx playwright test
```

Expected: All 25 tests pass.

**Step 3: Commit**

```bash
git add frontend/e2e/homescout.spec.ts
git commit -m "test: add freshness fields to E2E test mock data"
```

---

### Task 14: Update Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `backend/CLAUDE.md`

**Step 1: Update root CLAUDE.md**

Add to the Architecture section a note about market-driven scraping. Update the Data Sources box:

```
│  PostgreSQL (scraped data) │ apartments.json (fallback/mock)            │
│  MarketConfig (19 markets) │ Claude AI (scoring + comparison analysis)  │
│  Apify (apartments.com)   │ Redis (Celery task queue)                  │
```

Add a "Scraping Pipeline" section documenting:
- `dispatch_scrapes` (hourly), `decay_and_verify` (hourly), `cleanup_maintenance` (daily)
- Market tiers: hot (6h), standard (12h), cool (24h)
- Freshness confidence decay and verification

**Step 2: Update backend CLAUDE.md**

Update the beat schedule table and add notes about the dispatcher pattern.

**Step 3: Commit**

```bash
git add CLAUDE.md backend/CLAUDE.md
git commit -m "docs: update documentation for continuous scraping pipeline"
```
