import json
import os
from typing import List, Dict
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class ClaudeService:
    """Service for interacting with Claude AI to score apartments"""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = Anthropic(api_key=api_key)

    def score_apartments(
        self,
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

        Args:
            city: City to search in
            budget: Maximum monthly rent budget
            bedrooms: Number of bedrooms needed
            bathrooms: Number of bathrooms needed
            property_type: Desired property types
            move_in_date: Desired move-in date
            other_preferences: Additional user preferences
            apartments: List of apartment dictionaries to score

        Returns:
            List of apartment scores with match_score, reasoning, and highlights
        """

        # Format the prompt
        apartments_json = json.dumps(apartments, indent=2)

        # Build the user prompt from our template
        user_prompt = f"""Please analyze and score the following apartments based on my preferences:

## My Search Criteria:

**City:** {city}

**Budget:** ${budget}/month

**Bedrooms:** {bedrooms}

**Bathrooms:** {bathrooms}

**Property Type:** {property_type}

**Move-In Date:** {move_in_date}

**Additional Preferences:**
{other_preferences if other_preferences else "None specified"}

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

        # System prompt defines Claude's role and scoring guidelines
        system_prompt = """You are an expert apartment matching assistant for HomeScout, an app that helps young professionals find their ideal apartment efficiently. Your task is to analyze apartment listings against user preferences and provide accurate match scores.

Analyze each apartment based on:
1. Budget fit (how well the rent matches their budget)
2. Location desirability (neighborhood quality, safety, amenities)
3. Space requirements (bedrooms, bathrooms, square footage)
4. Property type preference
5. Move-in date availability
6. Additional preferences, which may include any of the following:
   - Pet policies: pet-friendly, pet play area, fee/rent for dog, fee/rent for cat
   - Parking: parking availability, fee for parking, garage, EV charging
   - Lease terms: deposit needed, furnished, short term lease (less than 1 year)
   - Building amenities: gym, swimming pool, tennis court, picnic area, sundeck, fireplace, day care, planned social activities
   - Unit features: walk-in closet, washer/dryer in apartment, refrigerator, microwave, air conditioner, hardwood floors, vinyl flooring
   - Utilities: Wi-Fi included, cable included, electric heating, gas heating, water view
   - Location & accessibility: landmark nearby, walk to market, public transport, 10 min walk to transportation, take out eateries nearby, walk score, bike score
   - Safety & security: safety, controlled access
   - Services: English/Spanish speaking staff, on-site maintenance, on-site management, online rent payment, dry cleaning service, pay for garbage pick up

For each apartment, provide:
- A match score (0-100%)
- A brief explanation (1-2 sentences) of why this score was assigned
- Key highlights that align with user preferences

Be honest and practical in your scoring. A perfect 100% match is rare. Most good matches will be in the 70-90% range."""

        try:
            # Call Claude API
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract response text
            response_text = message.content[0].text

            # Parse JSON from response (handle potential markdown code blocks)
            scores = self._parse_json_response(response_text)

            return scores

        except Exception as e:
            print(f"Error calling Claude API: {str(e)}")
            raise

    def _parse_json_response(self, response_text: str) -> List[Dict]:
        """
        Parse JSON from Claude's response, handling markdown code blocks.

        Args:
            response_text: Raw response text from Claude

        Returns:
            Parsed JSON as Python list
        """
        try:
            # Check if response is wrapped in markdown code blocks
            if "```json" in response_text:
                # Extract JSON from ```json ... ``` blocks
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                # Extract JSON from ``` ... ``` blocks
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            # Parse JSON
            scores = json.loads(response_text)

            # Validate structure
            if not isinstance(scores, list):
                raise ValueError("Response is not a JSON array")

            for score in scores:
                required_fields = ["apartment_id", "match_score", "reasoning", "highlights"]
                for field in required_fields:
                    if field not in score:
                        raise ValueError(f"Missing required field: {field}")

            return scores

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {str(e)}")
            print(f"Response text: {response_text}")
            raise ValueError(f"Invalid JSON response from Claude: {str(e)}")
        except Exception as e:
            print(f"Error parsing response: {str(e)}")
            raise
