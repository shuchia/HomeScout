"""Commute time calculation via the Google Distance Matrix API.

Mirrors the external-client + fail-open patterns used by the scraper services
(`services/scrapers/apify_service.py`) and the Redis caching pattern in
`services/apartment_service.py`. The feature is "free for everyone" but
restricted to the shortlist views (tour detail, compare, favorites), so cost
control rests entirely on: (1) aggressive 7-day Redis caching keyed on rounded
coordinates, and (2) a per-minute rate limit on the endpoint.

If GOOGLE_MAPS_API_KEY is unset the service is silently disabled — every public
method returns empty results and never raises.
"""
import os
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class CommuteService:
    DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
    MODES = ("driving", "transit", "walking")
    CACHE_TTL = 7 * 24 * 3600  # commute times are stable; cache a week
    MAX_ORIGINS = 25           # Distance Matrix per-request limit
    MAX_ELEMENTS = 100         # Distance Matrix per-request element limit

    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None
        self._redis: Optional[aioredis.Redis] = None
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_API_KEY not set — commute calculator disabled")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-load the HTTP client (distance lookups are quick — 15s timeout)."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._client

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            except Exception:
                self._redis = None
        return self._redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def get_commute_times_for_apartments(
        self,
        apartments: List[Dict[str, Any]],
        locations: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Map apartment_id -> list of per-location commute rows.

        Each apartment dict needs `id`, `latitude`, `longitude`.
        Each location dict needs `label`, `location_type`, `latitude`, `longitude`.
        Apartments/locations missing coordinates are skipped. Returns {} when the
        service is disabled or there's nothing computable — never raises.
        """
        result: Dict[str, List[Dict[str, Any]]] = {}
        if not self.enabled:
            return result

        locs = [
            l for l in locations
            if l.get("latitude") is not None and l.get("longitude") is not None
        ]
        if not locs:
            return result

        redis = await self._get_redis()

        # Split into fully-cached apartments (served from Redis) and the rest.
        uncached: List[Dict[str, Any]] = []
        for apt in apartments:
            alat, alng = apt.get("latitude"), apt.get("longitude")
            if alat is None or alng is None:
                continue
            rows: List[Dict[str, Any]] = []
            all_hit = True
            for loc in locs:
                cached = await self._cache_get(redis, alat, alng, loc["latitude"], loc["longitude"])
                if cached is None:
                    all_hit = False
                    break
                rows.append(self._row(loc, cached))
            if all_hit:
                result[apt["id"]] = rows
            else:
                uncached.append(apt)

        if uncached:
            result.update(await self._compute(uncached, locs, redis))
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _compute(
        self,
        apartments: List[Dict[str, Any]],
        locs: List[Dict[str, Any]],
        redis: Optional[aioredis.Redis],
    ) -> Dict[str, List[Dict[str, Any]]]:
        dests = "|".join(f"{l['latitude']},{l['longitude']}" for l in locs)
        # mode -> {(apartment_index, location_index): minutes}
        per_mode: Dict[str, Dict[tuple, Optional[int]]] = {m: {} for m in self.MODES}

        chunk_size = max(1, min(self.MAX_ORIGINS, self.MAX_ELEMENTS // max(1, len(locs))))
        for start in range(0, len(apartments), chunk_size):
            chunk = apartments[start:start + chunk_size]
            origins = "|".join(f"{a['latitude']},{a['longitude']}" for a in chunk)
            for mode in self.MODES:
                matrix = await self._call(origins, dests, mode)
                if not matrix:
                    continue
                for i, row in enumerate(matrix):
                    for j, element in enumerate(row):
                        per_mode[mode][(start + i, j)] = self._minutes(element)

        result: Dict[str, List[Dict[str, Any]]] = {}
        for ai, apt in enumerate(apartments):
            rows: List[Dict[str, Any]] = []
            for j, loc in enumerate(locs):
                value = {
                    "minutes_drive": per_mode["driving"].get((ai, j)),
                    "minutes_transit": per_mode["transit"].get((ai, j)),
                    "minutes_walk": per_mode["walking"].get((ai, j)),
                }
                rows.append(self._row(loc, value))
                # Only cache successful lookups. Caching an all-None result
                # (e.g. a transient REQUEST_DENIED or API outage) would poison
                # the entry for the full 7-day TTL.
                if any(v is not None for v in value.values()):
                    await self._cache_set(
                        redis, apt["latitude"], apt["longitude"],
                        loc["latitude"], loc["longitude"], value,
                    )
            result[apt["id"]] = rows
        return result

    async def _call(self, origins: str, destinations: str, mode: str) -> Optional[List[List[dict]]]:
        """Return a rows×elements matrix, or None on any failure (fail-open)."""
        try:
            resp = await self.client.get(
                self.DISTANCE_MATRIX_URL,
                params={
                    "origins": origins,
                    "destinations": destinations,
                    "mode": mode,
                    "units": "imperial",
                    "key": self.api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK":
                logger.warning(f"Distance Matrix status={data.get('status')} mode={mode}")
                return None
            return [row.get("elements", []) for row in data.get("rows", [])]
        except Exception as e:
            logger.warning(f"Distance Matrix call failed (mode={mode}): {e}")
            return None

    @staticmethod
    def _minutes(element: Optional[dict]) -> Optional[int]:
        if not element or element.get("status") != "OK":
            return None
        duration = element.get("duration", {}).get("value")  # seconds
        return round(duration / 60) if duration is not None else None

    @staticmethod
    def _row(loc: Dict[str, Any], value: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "label": loc["label"],
            "location_type": loc["location_type"],
            "minutes_drive": value.get("minutes_drive"),
            "minutes_transit": value.get("minutes_transit"),
            "minutes_walk": value.get("minutes_walk"),
        }

    @staticmethod
    def _pair_key(alat: float, alng: float, llat: float, llng: float) -> str:
        # Round to ~11m so nearby listings share cache entries.
        raw = f"{round(alat, 4)},{round(alng, 4)},{round(llat, 4)},{round(llng, 4)}"
        # v2 prefix invalidates entries poisoned by the early REQUEST_DENIED
        # period (key was IP/referrer-restricted against the backend).
        return f"commute:v2:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    async def _cache_get(
        self, redis: Optional[aioredis.Redis], alat: float, alng: float, llat: float, llng: float,
    ) -> Optional[Dict[str, Any]]:
        if not redis:
            return None
        try:
            raw = await redis.get(self._pair_key(alat, alng, llat, llng))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _cache_set(
        self, redis: Optional[aioredis.Redis], alat: float, alng: float,
        llat: float, llng: float, value: Dict[str, Any],
    ) -> None:
        if not redis:
            return
        try:
            await redis.setex(self._pair_key(alat, alng, llat, llng), self.CACHE_TTL, json.dumps(value))
        except Exception:
            pass


# Module-level singleton (lazy client) — mirrors other service singletons.
commute_service = CommuteService()
