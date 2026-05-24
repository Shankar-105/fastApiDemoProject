import pytest
import fakeredis

from app.services import rate_limit_service


@pytest.mark.asyncio
async def test_token_bucket_allows_burst_then_rejects(monkeypatch):
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(rate_limit_service._redis_svc, "redis_client", redis_client)
    monkeypatch.setattr(rate_limit_service.time, "time", lambda: 1_000.0)

    allowed_1, retry_after_1 = await rate_limit_service._consume_token_bucket("rl:test", 2, 10)
    allowed_2, retry_after_2 = await rate_limit_service._consume_token_bucket("rl:test", 2, 10)
    allowed_3, retry_after_3 = await rate_limit_service._consume_token_bucket("rl:test", 2, 10)

    assert allowed_1 is True
    assert allowed_2 is True
    assert allowed_3 is False
    assert retry_after_1 == 1
    assert retry_after_2 == 1
    assert retry_after_3 >= 1


@pytest.mark.asyncio
async def test_token_bucket_refills_over_time(monkeypatch):
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(rate_limit_service._redis_svc, "redis_client", redis_client)

    clock = {"now": 1_000.0}
    monkeypatch.setattr(rate_limit_service.time, "time", lambda: clock["now"])

    first_allowed, _ = await rate_limit_service._consume_token_bucket("rl:refill", 2, 4)
    second_allowed, _ = await rate_limit_service._consume_token_bucket("rl:refill", 2, 4)
    third_allowed, retry_after = await rate_limit_service._consume_token_bucket("rl:refill", 2, 4)

    clock["now"] += 5.0
    after_refill_allowed, after_refill_retry = await rate_limit_service._consume_token_bucket("rl:refill", 2, 4)

    assert first_allowed is True
    assert second_allowed is True
    assert third_allowed is False
    assert retry_after >= 1
    assert after_refill_allowed is True
    assert after_refill_retry == 1
