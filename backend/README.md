# HomeScout Backend API

FastAPI backend for the HomeScout apartment finder application.

## Features

- 🏠 Search apartments by city, budget, bedrooms, bathrooms, and property type
- 🤖 AI-powered match scoring using Claude Messages API
- 📊 Returns top 10 ranked apartment recommendations
- 🔄 CORS enabled for frontend integration
- 📝 Auto-generated API documentation
- 🗄️ PostgreSQL database with JSON fallback mode
- 🕷️ Data collection from Zillow, Apartments.com, and Craigslist
- ⏰ Celery task scheduling for automated scraping
- 📈 Prometheus metrics and monitoring

## Tech Stack

- **FastAPI** - Modern Python web framework
- **Anthropic Claude API** - AI-powered apartment matching
- **PostgreSQL + SQLAlchemy** - Database with async support
- **Celery + Redis** - Task queue for background jobs
- **Apify / ScrapingBee** - Data collection services
- **Pydantic** - Data validation
- **Uvicorn** - ASGI server

## Setup

### 1. Install Dependencies

```bash
# Make sure you're in the backend directory
cd backend

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:

```
ANTHROPIC_API_KEY=your_actual_api_key_here
FRONTEND_URL=http://localhost:3000
```

**Get your API key:**
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create a new key

### 3. Run the Server

```bash
# From the backend directory
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

## Database Setup (Optional)

By default, HomeScout uses a static JSON file for apartment data. To enable PostgreSQL:

### 1. Install PostgreSQL

```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib
```

### 2. Create Database

```bash
createdb homescout
```

### 3. Configure Environment

Add to your `.env`:

```
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/homescout
```

### 4. Run Migrations

```bash
cd backend
alembic upgrade head
```

## Data Collection Setup (Optional)

To enable automated apartment data collection:

### 1. Start Redis

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis
```

### 2. Configure API Keys

Add to your `.env`:

```
# Apify - for Zillow and Apartments.com
APIFY_API_TOKEN=your_apify_token

# ScrapingBee - for Craigslist
SCRAPINGBEE_API_KEY=your_scrapingbee_key
```

### 3. Start Celery Worker

```bash
# In a separate terminal
cd backend
celery -A app.celery_app worker --loglevel=info
```

### 4. Start Celery Beat (Scheduler)

```bash
# In another terminal
cd backend
celery -A app.celery_app beat --loglevel=info
```

## API Endpoints

### Health Check

```bash
GET /health
```

### Search Apartments

```bash
POST /api/search
Content-Type: application/json

{
  "city": "San Francisco, CA",
  "budget": 3500,
  "bedrooms": 2,
  "bathrooms": 2,
  "property_type": "Apartment, Condo",
  "move_in_date": "2025-12-01",
  "other_preferences": "Pet-friendly, parking, in-unit laundry"
}
```

### Get Apartment Count

```bash
GET /api/apartments/count
```

### Get Apartment Statistics

```bash
GET /api/apartments/stats
```

### Data Collection Admin API

```bash
# Trigger manual scrape job
POST /api/admin/data-collection/jobs
{
  "source": "zillow",
  "city": "San Francisco",
  "state": "CA",
  "max_listings": 100
}

# List scrape jobs
GET /api/admin/data-collection/jobs

# Get job status
GET /api/admin/data-collection/jobs/{job_id}

# List data sources
GET /api/admin/data-collection/sources

# Update source configuration
PUT /api/admin/data-collection/sources/{source_id}

# Get collection metrics
GET /api/admin/data-collection/metrics

# Health check for all services
GET /api/admin/data-collection/health
```

### Prometheus Metrics

```bash
GET /metrics
```

## Testing with curl

```bash
# Health check
curl http://localhost:8000/health

# Search apartments
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "city": "San Francisco, CA",
    "budget": 3500,
    "bedrooms": 2,
    "bathrooms": 2,
    "property_type": "Apartment",
    "move_in_date": "2025-12-01",
    "other_preferences": "Pet-friendly with parking"
  }'

# Trigger a scrape job (requires database mode)
curl -X POST http://localhost:8000/api/admin/data-collection/jobs \
  -H "Content-Type: application/json" \
  -d '{"source": "zillow", "city": "San Francisco", "state": "CA"}'
```

## Interactive API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive API documentation where you can test endpoints directly in your browser.

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app and endpoints
│   ├── database.py                # SQLAlchemy async configuration
│   ├── celery_app.py              # Celery configuration
│   ├── models.py                  # Pydantic models (API)
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── apartment.py
│   │   ├── scrape_job.py
│   │   └── data_source.py
│   ├── routers/
│   │   └── data_collection.py     # Admin API endpoints
│   ├── services/
│   │   ├── claude_service.py      # Claude API integration
│   │   ├── apartment_service.py   # Apartment search logic
│   │   ├── scrapers/              # Data collection services
│   │   │   ├── base_scraper.py
│   │   │   ├── apify_service.py
│   │   │   └── scrapingbee_service.py
│   │   ├── normalization/         # Data normalization
│   │   │   ├── normalizer.py
│   │   │   └── address_standardizer.py
│   │   ├── deduplication/         # Duplicate detection
│   │   │   └── deduplicator.py
│   │   ├── storage/               # S3 image caching
│   │   │   └── s3_service.py
│   │   └── monitoring/            # Metrics and alerts
│   │       ├── metrics.py
│   │       └── alerts.py
│   ├── tasks/                     # Celery tasks
│   │   ├── scrape_tasks.py
│   │   └── maintenance_tasks.py
│   └── data/
│       └── apartments.json        # Mock apartment data (fallback)
├── alembic/                       # Database migrations
│   ├── env.py
│   └── versions/
├── .env                           # Environment variables (gitignored)
├── .env.example                   # Example env file
├── alembic.ini                    # Alembic configuration
├── requirements.txt
└── README.md
```

## How It Works

### Search Flow
1. **User sends search request** → API receives JSON with search criteria
2. **Filter apartments** → Basic filtering by city, budget, beds, baths, property type
3. **Claude AI scoring** → Filtered apartments are sent to Claude for intelligent matching
4. **Rank & return** → Top 10 apartments sorted by match score are returned

### Data Collection Flow
1. **Scheduled task triggers** → Celery beat schedules scraping jobs
2. **Scraper fetches data** → Apify/ScrapingBee retrieves listings
3. **Normalize data** → Address standardization, field validation
4. **Deduplicate** → Content hashing and fuzzy matching
5. **Store in database** → PostgreSQL with quality scoring

## Development Tips

### Watch for file changes

The `--reload` flag automatically restarts the server when code changes.

### View logs

The server prints logs to the console. Watch for:
- Incoming requests
- Claude API calls
- Any errors

### Running Tests

```bash
cd backend
pytest
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Common Issues

**Issue:** "ANTHROPIC_API_KEY environment variable not set"
**Solution:** Make sure your `.env` file exists and contains your API key.

**Issue:** "Address already in use"
**Solution:** Another process is using port 8000. Kill it or use a different port:
```bash
uvicorn app.main:app --reload --port 8001
```

**Issue:** "No apartments found"
**Solution:** Check that your city name matches the format in `apartments.json` (e.g., "San Francisco, CA" not just "San Francisco")

**Issue:** "Database connection failed"
**Solution:** Ensure PostgreSQL is running and DATABASE_URL is correct in .env

## Support

For issues or questions:
1. Check the API docs at `/docs`
2. Review the code comments
3. Check that your `.env` is configured correctly
