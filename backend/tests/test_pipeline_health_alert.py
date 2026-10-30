"""Tests for pushing pipeline-health problems out.

pipeline-health was pull-only — nothing called it — so it could only help
someone who already suspected a problem. From 2026-10-10 every scrape failed
for three weeks and prod search emptied out without anyone being told.
"""
import pytest

from app.tasks import maintenance_tasks as mt


class _FakeRedis:
    def __init__(self, store, broken=False):
        self.store = store
        self.broken = broken

    async def get(self, key):
        if self.broken:
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value.encode() if isinstance(value, str) else value

    async def aclose(self):
        return None


class _FakeAlerts:
    sent = []

    async def send_alert(self, title, message, severity, source):
        _FakeAlerts.sent.append((title, message))
        return True

    async def close(self):
        return None


@pytest.fixture
def harness(monkeypatch):
    import redis.asyncio as aioredis
    import app.routers.data_collection as dc
    import app.services.monitoring.alerts as alerts_mod

    state = {"problems": [], "store": {}, "redis_broken": False}

    async def fake_health():
        return {"healthy": not state["problems"], "problems": list(state["problems"])}

    monkeypatch.setattr(dc, "check_pipeline_health", fake_health)
    monkeypatch.setattr(
        aioredis, "from_url",
        lambda url: _FakeRedis(state["store"], state["redis_broken"]),
    )
    monkeypatch.setattr(alerts_mod, "AlertService", _FakeAlerts)
    _FakeAlerts.sent = []
    return state


async def test_healthy_sends_nothing(harness):
    result = await mt._alert_pipeline_health()
    assert result == {"healthy": True, "alerted": False}
    assert _FakeAlerts.sent == []


async def test_problems_are_sent(harness):
    harness["problems"] = ["market 'boston' has not ingested listings in 200h"]
    result = await mt._alert_pipeline_health()
    assert result["alerted"] is True
    assert len(_FakeAlerts.sent) == 1
    assert "boston" in _FakeAlerts.sent[0][1]


async def test_same_problem_with_a_bigger_number_does_not_realert(harness):
    harness["problems"] = ["market 'boston' has not ingested listings in 200h"]
    await mt._alert_pipeline_health()
    harness["problems"] = ["market 'boston' has not ingested listings in 201h"]
    result = await mt._alert_pipeline_health()
    assert result["alerted"] is False
    assert len(_FakeAlerts.sent) == 1


async def test_a_new_problem_realerts(harness):
    harness["problems"] = ["market 'boston' has not ingested listings in 200h"]
    await mt._alert_pipeline_health()
    harness["problems"].append("market 'nyc' last scrape failed")
    result = await mt._alert_pipeline_health()
    assert result["alerted"] is True
    assert len(_FakeAlerts.sent) == 2


async def test_redis_outage_alerts_anyway(harness):
    harness["redis_broken"] = True
    harness["problems"] = ["decay task has not succeeded in 5h"]
    result = await mt._alert_pipeline_health()
    assert result["alerted"] is True
