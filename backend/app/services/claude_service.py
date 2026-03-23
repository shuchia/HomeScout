import json
import os
from typing import List, Dict, Optional
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

    @staticmethod
    def prepare_apartment_for_scoring(apt: dict) -> dict:
        """Prepare apartment data for Claude scoring. No truncation."""
        return {
            "id": apt["id"],
            "address": apt.get("address", ""),
            "rent": apt.get("rent", 0),
            "bedrooms": apt.get("bedrooms", 0),
            "bathrooms": apt.get("bathrooms", 0),
            "sqft": apt.get("sqft", 0),
            "property_type": apt.get("property_type", ""),
            "available_date": apt.get("available_date", ""),
            "neighborhood": apt.get("neighborhood", ""),
            "description": apt.get("description", "") or "",
            "amenities": apt.get("amenities", []) or [],
            "data_quality_score": apt.get("data_quality_score"),
            "heuristic_score": apt.get("heuristic_score"),
        }

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

        slim_apartments = [
            self.prepare_apartment_for_scoring(apt) for apt in apartments
        ]

        apartments_json = json.dumps(slim_apartments, indent=2)

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
        system_prompt = """You are an expert apartment matching assistant for Snugd, an app that helps young professionals find their ideal apartment efficiently. Your task is to analyze apartment listings against user preferences and provide accurate match scores.

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

    def compare_apartments_with_analysis(
        self,
        apartments: List[Dict],
        preferences: str,
        search_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Deep head-to-head comparison of 2-3 apartments.
        Returns dict with winner, categories, and per-apartment scores.
        """
        slim_apartments = [
            self.prepare_apartment_for_scoring(apt) for apt in apartments
        ]

        apartments_json = json.dumps(slim_apartments, indent=2)

        context_section = ""
        if search_context:
            context_section = f"""## Original Search Criteria
City: {search_context.get('city', 'N/A')} | Budget: ${search_context.get('budget', 'N/A')}/mo | Bedrooms: {search_context.get('bedrooms', 'N/A')} | Bathrooms: {search_context.get('bathrooms', 'N/A')} | Type: {search_context.get('property_type', 'N/A')} | Move-in: {search_context.get('move_in_date', 'N/A')}

"""

        user_prompt = f"""{context_section}## What Matters Most to This User
{preferences}

## Apartments to Compare
{apartments_json}

Compare these apartments across categories. Always include Value, Space & Layout, and Amenities as standard categories. Add 1-3 custom categories based on what matters most to this user. Score each apartment 0-100 per category. Pick an overall winner.

Return a JSON object with this exact structure:
{{
  "winner": {{
    "apartment_id": "the-winning-id",
    "reason": "1-2 sentence explanation of why this apartment wins overall"
  }},
  "categories": ["Value", "Space & Layout", "Amenities", ...custom categories],
  "apartment_scores": [
    {{
      "apartment_id": "id",
      "overall_score": 85,
      "reasoning": "1-2 sentence overall assessment",
      "highlights": ["highlight 1", "highlight 2"],
      "category_scores": {{
        "Value": {{"score": 80, "note": "brief note"}},
        "Space & Layout": {{"score": 75, "note": "brief note"}},
        ...one entry per category
      }}
    }}
  ]
}}

Return valid JSON only, no additional text."""

        system_prompt = """You are an expert apartment comparison analyst for Snugd. Compare apartments head-to-head across multiple categories, considering the user's stated preferences and search criteria. Be specific and practical in your analysis. Scores should reflect genuine differences — don't give similar scores unless apartments are truly comparable in that category."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = message.content[0].text
            result = self._parse_comparison_response(response_text)
            return result

        except Exception as e:
            print(f"Error calling Claude API for comparison: {str(e)}")
            raise

    def generate_inquiry_email(
        self,
        apartment: dict,
        user_context: dict,
    ) -> dict:
        """Generate a personalized inquiry email for an apartment.

        Args:
            apartment: Apartment listing data (address, rent, beds, baths, amenities, etc.)
            user_context: User info (name, move_in_date, budget, preferences)

        Returns:
            {"subject": "...", "body": "..."}
        """
        apartment_json = json.dumps(apartment, indent=2)
        user_json = json.dumps(user_context, indent=2)

        system_prompt = (
            "You are a helpful assistant writing a polite, professional inquiry "
            "email about an apartment listing. The email should be warm but "
            "concise — landlords receive many inquiries."
        )

        user_prompt = f"""Write an inquiry email for the following apartment listing.

## Apartment Details
{apartment_json}

## About the Prospective Tenant
{user_json}

Instructions:
- Write a subject line and email body.
- Address the landlord/property manager politely.
- Mention the user's name, desired move-in date, and budget if provided.
- Reference specific apartment details (address, rent, beds/baths, amenities) to show genuine interest.
- Ask smart questions based on what is MISSING from the listing:
  - No sqft listed? Ask about the apartment size.
  - No pet policy mentioned? Ask about pets if the user mentioned pets in preferences.
  - No parking info? Ask about parking if relevant.
  - No utilities info? Ask what's included.
  - No lease term info? Ask about lease length and terms.
- Keep it to 150-250 words for the body.
- Be professional but personable.

Return ONLY a JSON object with "subject" and "body" fields. No additional text."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = message.content[0].text
            result = self._parse_dict_response(response_text)
            return result

        except Exception as e:
            print(f"Error calling Claude API for inquiry email: {str(e)}")
            raise

    def _parse_dict_response(self, response_text: str) -> dict:
        """Parse a JSON dict from Claude's response, handling markdown code blocks."""
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()

        result = json.loads(response_text)

        if not isinstance(result, dict):
            raise ValueError("Response is not a JSON object")

        return result

    def generate_day_plan(
        self,
        tours: list[dict],
        user_home_address: str | None = None,
    ) -> dict:
        """Optimize tour order for a day with multiple scheduled tours.

        Args:
            tours: List of tours with apartment address, scheduled_date, scheduled_time.
            user_home_address: Optional starting address for the user.

        Returns:
            {"tours_ordered": [...], "travel_notes": [...], "tips": [...]}
        """
        tours_json = json.dumps(tours, indent=2)

        system_prompt = (
            "You are a tour day planning assistant. Optimize the order of "
            "apartment tours for efficiency, considering location proximity "
            "and travel time."
        )

        home_section = ""
        if user_home_address:
            home_section = f"\n## Starting Address\n{user_home_address}\n"

        user_prompt = f"""Plan the most efficient tour day for the following apartment visits.
{home_section}
## Scheduled Tours
{tours_json}

Instructions:
- Suggest the optimal visiting order to minimize travel time.
- Estimate travel times between stops.
- Provide practical tips (e.g., "these two are 3 blocks apart — book back-to-back").
- Keep tips concise and actionable.

Return ONLY a JSON object with this structure:
{{
  "tours_ordered": [
    {{"apartment_id": "...", "address": "...", "suggested_time": "HH:MM", "order": 1}}
  ],
  "travel_notes": ["Note about travel between stop 1 and 2", ...],
  "tips": ["Practical tip 1", ...]
}}

Return valid JSON only, no additional text."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = message.content[0].text
            return self._parse_dict_response(response_text)

        except Exception as e:
            print(f"Error calling Claude API for day plan: {str(e)}")
            raise

    def enhance_note(
        self,
        raw_note: str,
        apartment_context: dict,
    ) -> dict:
        """Clean up a tour note — remove filler, structure it, suggest tags.

        Args:
            raw_note: The raw note text entered by the user.
            apartment_context: Apartment details for context.

        Returns:
            {"enhanced_text": "...", "suggested_tags": [{"tag": "...", "sentiment": "pro"|"con"}]}
        """
        apartment_json = json.dumps(apartment_context, indent=2)

        system_prompt = (
            "You are cleaning up rough apartment tour notes. The user jotted "
            "these down quickly during or after a tour. Remove filler words, "
            "fix grammar, structure into clear observations. Also suggest "
            "pro/con tags."
        )

        user_prompt = f"""Clean up and enhance the following tour note.

## Raw Note
{raw_note}

## Apartment Context
{apartment_json}

Instructions:
- Remove filler words and fix grammar.
- Structure into clear, concise observations.
- Suggest pro/con tags based on the content.
- Keep the enhanced text faithful to the original observations.

Return ONLY a JSON object with this structure:
{{
  "enhanced_text": "Cleaned up and structured note text...",
  "suggested_tags": [
    {{"tag": "Tag name", "sentiment": "pro"}},
    {{"tag": "Tag name", "sentiment": "con"}}
  ]
}}

Return valid JSON only, no additional text."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = message.content[0].text
            return self._parse_dict_response(response_text)

        except Exception as e:
            print(f"Error calling Claude API for note enhancement: {str(e)}")
            raise

    def generate_decision_brief(
        self,
        toured_apartments: list[dict],
        user_preferences: str | None = None,
    ) -> dict:
        """Synthesize all toured apartments into a decision brief.

        Args:
            toured_apartments: List of apartments with tour data (rating, tags, notes).
            user_preferences: Optional user preferences string.

        Returns:
            {
                "apartments": [{"apartment_id": "...", "ai_take": "...", "strengths": [...], "concerns": [...]}],
                "recommendation": {"apartment_id": "...", "reasoning": "..."}
            }
        """
        apartments_json = json.dumps(toured_apartments, indent=2)

        system_prompt = (
            "You are helping a renter make a final decision. They've toured "
            "multiple apartments and captured ratings, notes, and pro/con "
            "tags. Synthesize everything into a clear, actionable "
            "recommendation. Respect the user's own ratings — don't override "
            "their impressions, but add context."
        )

        preferences_section = ""
        if user_preferences:
            preferences_section = f"\n## User Preferences\n{user_preferences}\n"

        user_prompt = f"""Generate a decision brief for these toured apartments.
{preferences_section}
## Toured Apartments
{apartments_json}

Instructions:
- For each apartment, provide an AI take (1-2 sentence summary), strengths, and concerns.
- Weight the user's own ratings and tags heavily in your analysis.
- Pick a recommended apartment with clear reasoning.
- Be practical and actionable.

Return ONLY a JSON object with this structure:
{{
  "apartments": [
    {{
      "apartment_id": "...",
      "ai_take": "1-2 sentence summary of this option",
      "strengths": ["strength 1", "strength 2"],
      "concerns": ["concern 1", "concern 2"]
    }}
  ],
  "recommendation": {{
    "apartment_id": "...",
    "reasoning": "Clear explanation of why this is the best choice"
  }}
}}

Return valid JSON only, no additional text."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = message.content[0].text
            return self._parse_dict_response(response_text)

        except Exception as e:
            print(f"Error calling Claude API for decision brief: {str(e)}")
            raise

    def _parse_comparison_response(self, response_text: str) -> Dict:
        """Parse the comparison analysis JSON from Claude's response."""
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()

        result = json.loads(response_text)

        for field in ["winner", "categories", "apartment_scores"]:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")

        return result
