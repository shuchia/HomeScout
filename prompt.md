AA# Claude Messages API Prompt for Match Scoring

## Purpose
This prompt is used to call the Claude Messages API to generate intelligent match scores between user preferences and apartment listings.

## API Integration Details

### Endpoint
```
POST https://api.anthropic.com/v1/messages
```

### Headers
```json
{
  "x-api-key": "YOUR_API_KEY",
  "anthropic-version": "2023-06-01",
  "content-type": "application/json"
}
```

## System Prompt

```
You are an expert apartment matching assistant for HomeScout, an app that helps young professionals find their ideal apartment efficiently. Your task is to analyze apartment listings against user preferences and provide accurate match scores.

Analyze each apartment based on:
1. Budget fit (how well the rent matches their budget)
2. Location desirability (neighborhood quality, safety, amenities)
3. Space requirements (bedrooms, bathrooms, square footage)
4. Property type preference
5. Move-in date availability
6. Additional preferences (amenities, pet-friendly, parking, etc.)

For each apartment, provide:
- A match score (0-100%)
- A brief explanation (1-2 sentences) of why this score was assigned
- Key highlights that align with user preferences

Be honest and practical in your scoring. A perfect 100% match is rare. Most good matches will be in the 70-90% range.
```

## User Prompt Template

```
Please analyze and score the following apartments based on my preferences:

## My Search Criteria:

**City:** {{city}}

**Budget:** ${{budget}}/month

**Bedrooms:** {{bedrooms}}

**Bathrooms:** {{bathrooms}}

**Property Type:** {{property_type}}

**Move-In Date:** {{move_in_date}}

**Additional Preferences:**
{{other_preferences}}

---

## Apartments to Evaluate:

{{apartments_json}}

---

Please return a JSON array with match scores for each apartment. For each apartment, include:
- apartment_id: The unique ID of the apartment
- match_score: A percentage from 0-100
- reasoning: A brief explanation (1-2 sentences)
- highlights: An array of 2-3 key features that match my preferences

Format your response as valid JSON only, with no additional text:

```json
[
  {
    "apartment_id": "apt-001",
    "match_score": 85,
    "reasoning": "Excellent location in your preferred neighborhood with rent slightly below budget. Has all requested amenities including in-unit laundry and parking.",
    "highlights": ["Under budget by $200/month", "In-unit washer/dryer", "Covered parking included"]
  }
]
```
```

## Example Usage

### Input Variables
```json
{
  "city": "San Francisco, CA",
  "budget": "3500",
  "bedrooms": "2",
  "bathrooms": "2",
  "property_type": "Apartment, Condo",
  "move_in_date": "2025-12-01",
  "other_preferences": "Must have in-unit washer/dryer, parking, pet-friendly for a small dog, close to public transit. Would prefer modern building with gym."
}
```

### Apartments JSON Format
```json
[
  {
    "id": "apt-001",
    "address": "123 Market St, San Francisco, CA 94103",
    "rent": 3400,
    "bedrooms": 2,
    "bathrooms": 2,
    "sqft": 1100,
    "property_type": "Apartment",
    "available_date": "2025-11-15",
    "amenities": ["In-unit laundry", "Parking", "Pet-friendly", "Gym", "Rooftop deck"],
    "neighborhood": "SoMa",
    "description": "Modern luxury apartment in the heart of SoMa. Walking distance to BART and tech offices."
  },
  {
    "id": "apt-002",
    "address": "456 Valencia St, San Francisco, CA 94110",
    "rent": 3600,
    "bedrooms": 2,
    "bathrooms": 1,
    "sqft": 950,
    "property_type": "Apartment",
    "available_date": "2025-12-01",
    "amenities": ["Shared laundry", "Street parking", "Pet-friendly"],
    "neighborhood": "Mission District",
    "description": "Charming Victorian apartment in vibrant Mission District. Close to restaurants and nightlife."
  }
]
```

### Expected Output
```json
[
  {
    "apartment_id": "apt-001",
    "match_score": 92,
    "reasoning": "Nearly perfect match with rent under budget, all must-have amenities including in-unit laundry and parking, pet-friendly, and has desired gym. Available earlier than needed.",
    "highlights": ["Under budget by $100/month", "All must-have amenities included", "Modern building with gym"]
  },
  {
    "apartment_id": "apt-002",
    "match_score": 68,
    "reasoning": "Good location but rent is over budget, only 1 bathroom instead of 2, and lacks in-unit laundry and dedicated parking. Still pet-friendly and available on target date.",
    "highlights": ["Available on exact move-in date", "Pet-friendly for your dog", "Popular Mission District location"]
  }
]
```

## Implementation Notes

### Python (FastAPI) Example
```python
import anthropic
import json
from typing import List, Dict

async def score_apartments(
    city: str,
    budget: int,
    bedrooms: int,
    bathrooms: int,
    property_type: str,
    move_in_date: str,
    other_preferences: str,
    apartments: List[Dict]
) -> List[Dict]:
    """
    Call Claude API to score apartments based on user preferences.
    """
    client = anthropic.Anthropic(api_key="YOUR_API_KEY")

    # Format the prompt
    apartments_json = json.dumps(apartments, indent=2)

    user_prompt = f"""Please analyze and score the following apartments based on my preferences:

## My Search Criteria:

**City:** {city}

**Budget:** ${budget}/month

**Bedrooms:** {bedrooms}

**Bathrooms:** {bathrooms}

**Property Type:** {property_type}

**Move-In Date:** {move_in_date}

**Additional Preferences:**
{other_preferences}

---

## Apartments to Evaluate:

{apartments_json}

---

Please return a JSON array with match scores for each apartment. For each apartment, include:
- apartment_id: The unique ID of the apartment
- match_score: A percentage from 0-100
- reasoning: A brief explanation (1-2 sentences)
- highlights: An array of 2-3 key features that match my preferences

Format your response as valid JSON only, with no additional text."""

    system_prompt = """You are an expert apartment matching assistant for HomeScout, an app that helps young professionals find their ideal apartment efficiently. Your task is to analyze apartment listings against user preferences and provide accurate match scores.

Analyze each apartment based on:
1. Budget fit (how well the rent matches their budget)
2. Location desirability (neighborhood quality, safety, amenities)
3. Space requirements (bedrooms, bathrooms, square footage)
4. Property type preference
5. Move-in date availability
6. Additional preferences (amenities, pet-friendly, parking, etc.)

For each apartment, provide:
- A match score (0-100%)
- A brief explanation (1-2 sentences) of why this score was assigned
- Key highlights that align with user preferences

Be honest and practical in your scoring. A perfect 100% match is rare. Most good matches will be in the 70-90% range."""

    # Call Claude API
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    # Parse response
    response_text = message.content[0].text

    # Extract JSON from response (handle potential markdown code blocks)
    if "```json" in response_text:
        json_start = response_text.find("```json") + 7
        json_end = response_text.find("```", json_start)
        response_text = response_text[json_start:json_end].strip()
    elif "```" in response_text:
        json_start = response_text.find("```") + 3
        json_end = response_text.find("```", json_start)
        response_text = response_text[json_start:json_end].strip()

    scores = json.loads(response_text)

    return scores
```

## Best Practices

1. **Token Management:** Each API call costs tokens. For large datasets, score apartments in batches of 10-20.

2. **Error Handling:** Always wrap API calls in try-catch blocks. Handle rate limits and network errors gracefully.

3. **Caching:** Consider caching results for identical searches to reduce API costs.

4. **Prompt Refinement:** Test the prompt with various user inputs and adjust based on response quality.

5. **Response Validation:** Always validate that Claude returns valid JSON before parsing.

6. **Cost Optimization:** Use Claude Haiku for development/testing, Sonnet for production.

## Scoring Guidelines (for prompt tuning)

- **90-100%:** Nearly perfect match (all major requirements + most preferences)
- **75-89%:** Excellent match (all major requirements + some preferences)
- **60-74%:** Good match (most requirements met, minor compromises)
- **40-59%:** Moderate match (some requirements met, significant compromises)
- **Below 40%:** Poor match (many requirements not met)
