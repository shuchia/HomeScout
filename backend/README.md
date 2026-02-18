# HomeScout Backend API

FastAPI backend for the HomeScout apartment finder application.

## Features

- 🏠 Search apartments by city, budget, bedrooms, bathrooms, and property type
- 🤖 AI-powered match scoring using Claude Messages API
- 📊 Returns top 10 ranked apartment recommendations
- 🔄 CORS enabled for frontend integration
- 📝 Auto-generated API documentation

## Tech Stack

- **FastAPI** - Modern Python web framework
- **Anthropic Claude API** - AI-powered apartment matching
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
│   ├── models.py                  # Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── claude_service.py      # Claude API integration
│   │   └── apartment_service.py   # Apartment search logic
│   └── data/
│       └── apartments.json        # Mock apartment data
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Example env file
├── .gitignore
├── requirements.txt
└── README.md
```

## How It Works

1. **User sends search request** → API receives JSON with search criteria
2. **Filter apartments** → Basic filtering by city, budget, beds, baths, property type
3. **Claude AI scoring** → Filtered apartments are sent to Claude for intelligent matching
4. **Rank & return** → Top 10 apartments sorted by match score are returned

## Development Tips

### Watch for file changes

The `--reload` flag automatically restarts the server when code changes.

### View logs

The server prints logs to the console. Watch for:
- Incoming requests
- Claude API calls
- Any errors

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

## Next Steps

1. ✅ Get API running locally
2. ✅ Test endpoints with curl or Swagger UI
3. 🔲 Build Next.js frontend
4. 🔲 Connect frontend to this API
5. 🔲 Deploy to production

## Support

For issues or questions:
1. Check the API docs at `/docs`
2. Review the code comments
3. Check that your `.env` is configured correctly
