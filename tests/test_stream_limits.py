"""Concurrent-stream limiting: slot accounting, cleanup on every exit path, HTTP behaviour."""

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.api.routes.ai as ai_routes
from src.api.main import app
from src.auth.dependencies import get_current_user
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import AiUsageDaily, Chat, User
from src.schemas.ai import ChatRequest
from src.security.stream_limiter import StreamLimiter, stream_limiter
from src.services import ai_quota_service as quota


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


# ------------------------------------------------------------------ limiter unit
def test_limiter_admits_up_to_the_maximum_and_rejects_the_rest():
    lim = StreamLimiter()
    slots = [lim.acquire(3) for _ in range(3)]
    assert all(slots) and lim.active() == 3
    assert lim.acquire(3) is None
    assert lim.active() == 3


def test_released_slot_can_be_reused():
    lim = StreamLimiter()
    first = lim.acquire(1)
    assert lim.acquire(1) is None
    first.release()
    assert lim.active() == 0
    assert lim.acquire(1) is not None


def test_double_release_does_not_free_somebody_elses_slot():
    lim = StreamLimiter()
    a, b = lim.acquire(2), lim.acquire(2)
    a.release()
    a.release()
    assert lim.active() == 1
    assert lim.acquire(2) is not None
    assert lim.acquire(2) is None  # b is still held
    b.release()


def test_leaked_slot_is_reclaimed_after_its_lease():
    clock = FakeClock()
    lim = StreamLimiter(clock=clock, lease_seconds=300)
    lim.acquire(1)  # owner vanished and never released
    assert lim.acquire(1) is None
    clock.now = 299
    assert lim.acquire(1) is None
    clock.now = 300
    assert lim.acquire(1) is not None
    assert lim.active() == 1


def test_many_acquire_release_cycles_leave_nothing_occupied():
    lim = StreamLimiter()
    for _ in range(500):
        lim.acquire(3).release()
    assert lim.active() == 0


def test_limiter_is_thread_safe_at_the_boundary():
    lim = StreamLimiter()
    results, barrier, lock = [], threading.Barrier(30), threading.Lock()

    def worker():
        barrier.wait()
        slot = lim.acquire(3)
        with lock:
            results.append(slot)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert sum(1 for r in results if r is not None) == 3
    assert lim.active() == 3


# -------------------------------------------------- generator cleanup (no HTTP)
@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(bind=engine)
    Session_ = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    seed = Session_()
    user = User(username="u1", email="u1@example.com", hashed_password="x")
    seed.add(user)
    seed.commit()
    user_id = user.id
    seed.close()
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 100)
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_GLOBAL", 1000)
    monkeypatch.setattr(settings, "AI_DAILY_TOKENS_GLOBAL", 10_000_000)
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    yield SimpleNamespace(engine=engine, Session=Session_, user_id=user_id)
    app.dependency_overrides.clear()
    engine.dispose()


def usage_of(env):
    with Session(bind=env.engine) as s:
        row = s.query(AiUsageDaily).filter_by(scope=f"user:{env.user_id}").first()
        return (row.requests, row.tokens) if row else (0, 0)


def start_generator(env, monkeypatch, stream):
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stream)
    db = env.Session()
    user = db.get(User, env.user_id)
    reservation = quota.reserve(db, env.user_id, 6500)
    slot = stream_limiter.acquire(3)
    assert stream_limiter.active() == 1
    gen = ai_routes.generate_stream(db, user, ChatRequest(message="hi"), None, [], [], {}, slot, reservation)
    return gen, db


def chunks_then(*items, fail=None):
    def stream(outcome=None, **kwargs):
        outcome["prompt_chars"] = 400
        for item in items:
            yield item
        if fail:
            raise RuntimeError(fail)
        outcome["finish_reason"] = "stop"

    return stream


def test_slot_and_quota_are_settled_after_success(env, monkeypatch):
    gen, _ = start_generator(env, monkeypatch, chunks_then("a" * 400))
    out = "".join(gen)
    assert out.endswith("stop")
    assert stream_limiter.active() == 0
    assert usage_of(env) == (1, (400 + 400) // 4)


def test_slot_is_released_when_the_provider_raises_midway(env, monkeypatch):
    gen, _ = start_generator(env, monkeypatch, chunks_then("part " * 20, fail="boom sk-SECRET"))
    out = "".join(gen)
    assert out.endswith("error") and "sk-SECRET" not in out
    assert stream_limiter.active() == 0
    assert usage_of(env)[0] == 1 and usage_of(env)[1] > 0


def test_slot_is_released_and_quota_refunded_when_the_provider_fails_immediately(env, monkeypatch):
    gen, _ = start_generator(env, monkeypatch, chunks_then(fail="boom"))
    assert "".join(gen).endswith("error")
    assert stream_limiter.active() == 0
    assert usage_of(env) == (0, 0)


def test_slot_is_released_and_partial_output_counted_on_client_disconnect(env, monkeypatch):
    gen, _ = start_generator(env, monkeypatch, chunks_then("c" * 400, "d" * 400))
    assert next(gen) == "c" * 400
    gen.close()  # what a disconnect/cancellation does to a running generator
    assert stream_limiter.active() == 0
    assert usage_of(env) == (1, (400 + 400) // 4)


def test_disconnect_before_any_output_refunds_the_quota(env, monkeypatch):
    started = threading.Event()

    def stream(outcome=None, **kwargs):
        outcome["prompt_chars"] = 400
        started.set()
        yield ""  # nothing useful produced yet
        yield "late"

    gen, _ = start_generator(env, monkeypatch, stream)
    next(gen)
    gen.close()
    assert stream_limiter.active() == 0
    assert usage_of(env) == (0, 0)


def test_cleanup_is_idempotent_across_repeated_close(env, monkeypatch):
    gen, _ = start_generator(env, monkeypatch, chunks_then("e" * 40, "f" * 40))
    next(gen)
    gen.close()
    gen.close()
    assert stream_limiter.active() == 0
    assert usage_of(env)[0] == 1


# -------------------------------------------------------------------- over HTTP
@pytest.fixture
def http(env, monkeypatch):
    def override_get_db():
        s = env.Session()
        try:
            yield s
        finally:
            s.close()

    def override_user():
        with env.Session() as s:
            return s.get(User, env.user_id)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    monkeypatch.setattr(settings, "RATE_LIMIT_AI_PER_MINUTE", 1000)
    return TestClient(app, raise_server_exceptions=False)


def post_stream(client):
    return client.post("/ai/chat/stream", json={"message": "hello"})


def test_excess_stream_is_rejected_with_429_before_any_provider_call_or_quota_use(env, http, monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_CONCURRENT_STREAMS", 1)
    calls = []
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", lambda **kw: calls.append(kw) or iter(["x"]))
    held = stream_limiter.acquire(1)  # another stream is in flight
    blocked = post_stream(http)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == str(ai_routes.STREAM_BUSY_RETRY_AFTER_SECONDS)
    assert calls == [] and usage_of(env) == (0, 0)
    held.release()
    assert post_stream(http).status_code == 200


@pytest.mark.parametrize("fail", [False, True])
def test_slot_is_free_after_an_http_stream_ends_normally_or_with_a_provider_error(env, http, monkeypatch, fail):
    monkeypatch.setattr(settings, "AI_MAX_CONCURRENT_STREAMS", 1)

    def stream(outcome=None, **kwargs):
        yield "hello"
        if fail:
            raise RuntimeError("provider exploded")
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stream)
    assert post_stream(http).status_code == 200
    assert stream_limiter.active() == 0
    assert post_stream(http).status_code == 200  # the slot really is reusable


def test_quota_rejection_does_not_leak_a_slot(env, http, monkeypatch):
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 1)
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", lambda **kw: iter(["x"]))
    assert post_stream(http).status_code == 200
    assert post_stream(http).status_code == 429
    assert stream_limiter.active() == 0


def test_real_concurrent_streams_are_capped_and_all_slots_come_back(env, http, monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_CONCURRENT_STREAMS", 3)
    monkeypatch.setattr(settings, "AI_MAX_CONCURRENT_STREAMS_PER_USER", 3)  # one test user: exercise the global cap
    gate = threading.Event()

    def stream(outcome=None, **kwargs):
        yield "start "
        gate.wait(10)
        yield "end"
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stream)
    statuses = []

    def run():
        statuses.append(post_stream(TestClient(app, raise_server_exceptions=False)).status_code)

    threads = [threading.Thread(target=run) for _ in range(3)]
    [t.start() for t in threads]
    deadline = time.time() + 10
    while stream_limiter.active() < 3 and time.time() < deadline:
        time.sleep(0.02)
    assert stream_limiter.active() == 3
    assert post_stream(http).status_code == 429  # the fourth is turned away while three run
    gate.set()
    [t.join(15) for t in threads]
    assert sorted(statuses) == [200, 200, 200]
    assert stream_limiter.active() == 0
    assert post_stream(http).status_code == 200


# ------------------------------------------------------------------ lease renewal
def test_renewal_keeps_a_long_active_stream_from_losing_its_slot():
    clock = FakeClock()
    lim = StreamLimiter(clock=clock, lease_seconds=300, max_stream_seconds=10_000)
    slot = lim.acquire(1)
    for _ in range(40):  # 40 * 100 s = 4000 s of activity, far beyond one lease
        clock.now += 100
        assert slot.renew() is True
        assert lim.acquire(1) is None  # nobody can take the slot while it is active
    assert lim.active() == 1


def test_silent_stream_loses_its_slot_after_the_idle_lease_and_must_stop():
    clock = FakeClock()
    lim = StreamLimiter(clock=clock, lease_seconds=300)
    slot = lim.acquire(1)
    clock.now = 300
    other = lim.acquire(1)
    assert other is not None  # documented limit: a stalled stream's slot is reclaimed
    assert slot.renew() is False  # the stalled stream is told to stop
    other.release()
    assert lim.active() == 0


def test_stream_over_the_maximum_duration_is_ended_even_if_active():
    clock = FakeClock()
    lim = StreamLimiter(clock=clock, lease_seconds=300, max_stream_seconds=600)
    slot = lim.acquire(1)
    clock.now = 250
    assert slot.renew() is True
    clock.now = 500
    assert slot.renew() is True
    clock.now = 650
    assert slot.renew() is False
    assert lim.active() == 0 and lim.acquire(1) is not None


def test_renew_after_release_is_false_and_release_stays_idempotent():
    lim = StreamLimiter()
    slot = lim.acquire(1)
    slot.release()
    assert slot.renew() is False
    slot.release()
    other = lim.acquire(1)
    assert slot.renew() is False  # a stale handle never renews somebody else's slot
    assert lim.active() == 1 and other is not None


def test_renewal_is_thread_safe_alongside_acquire_and_release():
    lim = StreamLimiter()
    slot = lim.acquire(2)
    errors = []

    def renewer():
        try:
            for _ in range(500):
                assert slot.renew() is True
        except AssertionError as exc:  # pragma: no cover
            errors.append(exc)

    def churn():
        for _ in range(500):
            s = lim.acquire(2)
            if s:
                s.release()

    threads = [threading.Thread(target=f) for f in (renewer, renewer, churn, churn)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert not errors and lim.active() == 1


def test_long_running_generator_keeps_its_slot_for_the_whole_stream(env, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(stream_limiter, "_clock", clock)

    def slow_stream(outcome=None, **kwargs):
        outcome["prompt_chars"] = 400
        for _ in range(20):
            clock.now += 120  # 2400 s in total: eight times the idle lease
            yield "tok "
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", slow_stream)
    monkeypatch.setattr(stream_limiter, "_max", 10_000)
    db = env.Session()
    user = db.get(User, env.user_id)
    reservation = quota.reserve(db, env.user_id, 6500)
    slot = stream_limiter.acquire(1)
    gen = ai_routes.generate_stream(db, user, ChatRequest(message="hi"), None, [], [], {}, slot, reservation)
    seen_full = []
    out = []
    for piece in gen:
        out.append(piece)
        seen_full.append(stream_limiter.acquire(1) is None)  # the cap of 1 holds throughout
    assert all(seen_full)
    assert out[-1].endswith("stop")
    assert stream_limiter.active() == 0


def test_generator_stops_and_cleans_up_when_the_lease_is_lost(env, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(stream_limiter, "_clock", clock)

    def stalling_stream(outcome=None, **kwargs):
        outcome["prompt_chars"] = 400
        yield "first "
        clock.now += 301  # silent for longer than the idle lease
        yield "late chunk"
        yield "never delivered"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stalling_stream)
    db = env.Session()
    user = db.get(User, env.user_id)
    reservation = quota.reserve(db, env.user_id, 6500)
    slot = stream_limiter.acquire(1)
    out = "".join(ai_routes.generate_stream(db, user, ChatRequest(message="hi"), None, [], [], {}, slot, reservation))
    assert "never delivered" not in out and out.endswith("timeout")
    assert stream_limiter.active() == 0
    assert usage_of(env)[0] == 1  # partial output is counted


# ------------------------------------------------ production defaults (fake clock only)
def test_production_default_constants_are_300_idle_and_600_absolute():
    from src.security import stream_limiter as module

    assert module.DEFAULT_LEASE_SECONDS == 300
    assert module.DEFAULT_MAX_STREAM_SECONDS == 600
    fresh = StreamLimiter()
    assert (fresh._lease, fresh._max) == (300, 600)
    assert (stream_limiter._lease, stream_limiter._max) == (300, 600)  # the singleton the routes use


@pytest.mark.parametrize("step", [10, 100, 299])
def test_actively_renewed_stream_is_terminated_at_the_600_second_absolute_limit(step):
    clock = FakeClock()
    lim = StreamLimiter(clock=clock)  # production lease and ceiling; only the clock is fake
    slot = lim.acquire(1)
    t = 0
    while t + step < 600:
        t += step
        clock.now = t
        assert slot.renew() is True, f"terminated early at {t}s"
        assert lim.acquire(1) is None  # still held and still protecting the cap
    clock.now = 600  # a chunk arrives exactly at the ceiling, well inside the idle lease
    assert slot.renew() is False
    assert lim.active() == 0  # the slot is freed
    assert slot.renew() is False  # and stays dead: renewal cannot resurrect it
    assert lim.acquire(1) is not None


def test_599_seconds_is_still_allowed_and_601_is_not_with_production_defaults():
    clock = FakeClock()
    lim = StreamLimiter()
    lim._clock = clock
    slot = lim.acquire(1)
    clock.now = 299
    assert slot.renew() is True
    clock.now = 598
    assert slot.renew() is True
    clock.now = 599.9
    assert slot.renew() is True
    clock.now = 600.1
    assert slot.renew() is False


def test_generate_stream_emits_the_timeout_marker_and_frees_the_slot_at_600_seconds(env, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(stream_limiter, "_clock", clock)  # ONLY the clock: lease 300 and ceiling 600 stay
    assert (stream_limiter._lease, stream_limiter._max) == (300, 600)
    delivered = []

    def steady_stream(outcome=None, **kwargs):
        outcome["prompt_chars"] = 400
        for i in range(1, 100):
            clock.now = i * 100.0  # a chunk every 100 s: never idle for anywhere near 300 s
            yield f"chunk{i} "
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", steady_stream)
    db = env.Session()
    user = db.get(User, env.user_id)
    reservation = quota.reserve(db, env.user_id, 6500)
    slot = stream_limiter.acquire(1)
    assert stream_limiter.active() == 1
    gen = ai_routes.generate_stream(db, user, ChatRequest(message="hi"), None, [], [], {}, slot, reservation)
    for piece in gen:
        delivered.append(piece)
        if not piece.startswith(ai_routes.STREAM_END_MARKER):
            assert stream_limiter.acquire(1) is None  # slot held for as long as the stream is delivering

    assert delivered[:-1] == [f"chunk{i} " for i in range(1, 6)]  # t=100..500 delivered; t=600 refused
    assert delivered[-1] == f"{ai_routes.STREAM_END_MARKER}timeout"
    assert stream_limiter.active() == 0  # slot released
    assert reservation.finished is True  # quota settled for what was produced
    assert usage_of(env)[0] == 1 and usage_of(env)[1] > 0


# ------------------------------------------- saved history holds only delivered chunks
def saved_responses(env):
    with Session(bind=env.engine) as s:
        return [c.ai_response for c in s.query(Chat).order_by(Chat.id)]


def run_generator(env, monkeypatch, stream, clock=None):
    """Drive the real generate_stream to its end; returns (pieces the client received, reservation)."""
    if clock is not None:
        monkeypatch.setattr(stream_limiter, "_clock", clock)  # only the clock: 300 s lease, 600 s ceiling stay
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stream)
    db = env.Session()
    user = db.get(User, env.user_id)
    reservation = quota.reserve(db, env.user_id, 6500)
    slot = stream_limiter.acquire(1)
    gen = ai_routes.generate_stream(db, user, ChatRequest(message="hi"), None, [], [], {}, slot, reservation)
    return list(gen), reservation


def timed_stream(clock, plan, finish="stop"):
    """plan = [(time the chunk arrives, text), ...]"""
    def stream(outcome=None, **kwargs):
        outcome["prompt_chars"] = 400
        for at, text in plan:
            clock.now = at
            yield text
        outcome["finish_reason"] = finish
    return stream


def test_delivered_chunks_are_saved_in_their_original_order(env, monkeypatch):
    pieces, reservation = run_generator(env, monkeypatch, chunks_then("alpha ", "beta ", "gamma ", "delta"))
    assert pieces[:-1] == ["alpha ", "beta ", "gamma ", "delta"]
    assert pieces[-1] == f"{ai_routes.STREAM_END_MARKER}stop"
    assert saved_responses(env) == ["alpha beta gamma delta"]  # same text, same order, no note on "stop"
    assert stream_limiter.active() == 0 and reservation.finished is True


def test_chunk_rejected_by_renew_is_not_saved_and_not_delivered(env, monkeypatch):
    clock = FakeClock()
    plan = [(100, "ok1 "), (300, "ok2 "), (500, "ok3 "), (600, "TRIGGER-CHUNK "), (700, "AFTER-CHUNK")]
    pieces, _ = run_generator(env, monkeypatch, timed_stream(clock, plan), clock)
    assert pieces[:-1] == ["ok1 ", "ok2 ", "ok3 "]  # the client never saw the chunk that arrived at t=600
    [saved] = saved_responses(env)
    assert saved == "ok1 ok2 ok3 " + ai_routes.INCOMPLETE_NOTES["timeout"]
    assert "TRIGGER" not in saved and "AFTER" not in saved


def test_timeout_marker_follows_the_existing_contract_after_a_rejected_chunk(env, monkeypatch):
    clock = FakeClock()
    plan = [(100, "ok1 "), (600, "TRIGGER-CHUNK ")]
    pieces, _ = run_generator(env, monkeypatch, timed_stream(clock, plan), clock)
    marker = ai_routes.STREAM_END_MARKER
    assert pieces[-1] == f"{marker}timeout"                 # one in-band marker, last, status "timeout"
    assert sum(1 for p in pieces if marker in p) == 1       # never twice, never mixed into a text chunk
    [saved] = saved_responses(env)
    assert marker not in saved                               # the marker is a transport signal, not history
    assert saved.endswith(ai_routes.INCOMPLETE_NOTES["timeout"])


def test_slot_is_released_and_quota_settled_after_a_timeout_with_a_rejected_chunk(env, monkeypatch):
    clock = FakeClock()
    plan = [(100, "x" * 400), (600, "y" * 400)]
    pieces, reservation = run_generator(env, monkeypatch, timed_stream(clock, plan), clock)
    assert pieces[-1].endswith("timeout")
    assert stream_limiter.active() == 0                      # slot freed
    assert stream_limiter.acquire(1) is not None             # and reusable
    assert reservation.finished is True
    # Quota is settled on everything the provider generated (it was paid for), delivered or not:
    # prompt 400 chars + 800 generated chars = 1200 / 4 = 300 tokens, request counted once.
    assert usage_of(env) == (1, 300)


def test_rejected_first_chunk_saves_nothing_but_the_request_stays_counted(env, monkeypatch):
    clock = FakeClock()
    plan = [(600, "FIRST-AND-REJECTED" + "z" * 382)]
    pieces, reservation = run_generator(env, monkeypatch, timed_stream(clock, plan), clock)
    assert pieces == [f"{ai_routes.STREAM_END_MARKER}timeout"]
    assert saved_responses(env) == []                        # nothing was delivered, so no history row
    assert reservation.finished is True and stream_limiter.active() == 0
    assert usage_of(env) == (1, (400 + 400) // 4)            # settled, not refunded: output was generated


def test_chunk_after_an_idle_lease_expiry_is_not_saved(env, monkeypatch):
    clock = FakeClock()
    plan = [(10, "early "), (400, "LATE-AFTER-SILENCE ")]    # 390 s of silence > the 300 s idle lease
    pieces, _ = run_generator(env, monkeypatch, timed_stream(clock, plan), clock)
    assert pieces[:-1] == ["early "] and pieces[-1].endswith("timeout")
    [saved] = saved_responses(env)
    assert "LATE" not in saved and saved.startswith("early ")
    assert stream_limiter.active() == 0


def test_provider_error_after_delivered_chunks_saves_only_what_was_delivered(env, monkeypatch):
    pieces, _ = run_generator(env, monkeypatch, chunks_then("one ", "two ", fail="boom"))
    assert pieces[:-1] == ["one ", "two "] and pieces[-1].endswith("error")
    [saved] = saved_responses(env)
    assert saved == "one two " + ai_routes.INCOMPLETE_NOTES["error"]
    assert stream_limiter.active() == 0


def test_client_disconnect_saves_no_history_and_still_counts_the_generated_chunk(env, monkeypatch):
    gen, _ = start_generator(env, monkeypatch, chunks_then("c" * 400, "d" * 400))
    assert next(gen) == "c" * 400
    gen.close()  # disconnect while that chunk was in flight
    assert saved_responses(env) == []                        # unchanged behaviour: nothing persisted on disconnect
    assert stream_limiter.active() == 0
    assert usage_of(env) == (1, (400 + 400) // 4)            # quota semantics unchanged


# ------------------------------------------------------ per-owner cap (one user, one stream)
def test_owner_cap_is_enforced_before_the_global_cap_and_reports_why():
    lim = StreamLimiter()
    a1, why = lim.try_acquire(3, owner="a", max_per_owner=1)
    assert a1 is not None and why is None
    assert lim.try_acquire(3, owner="a", max_per_owner=1) == (None, "owner")
    b1, _ = lim.try_acquire(3, owner="b", max_per_owner=1)
    c1, _ = lim.try_acquire(3, owner="c", max_per_owner=1)
    assert b1 is not None and c1 is not None and lim.active() == 3
    assert lim.try_acquire(3, owner="d", max_per_owner=1) == (None, "full")
    assert lim.try_acquire(3, owner="a", max_per_owner=1) == (None, "owner")


def test_one_owner_can_never_leave_fewer_than_n_minus_one_slots_for_others():
    lim = StreamLimiter()
    held = [lim.try_acquire(3, owner="greedy", max_per_owner=1)[0] for _ in range(10)]
    assert sum(h is not None for h in held) == 1
    assert lim.try_acquire(3, owner="x", max_per_owner=1)[0] is not None
    assert lim.try_acquire(3, owner="y", max_per_owner=1)[0] is not None


def test_releasing_frees_the_owner_and_double_release_does_not_free_another_streams_owner_slot():
    lim = StreamLimiter()
    first, _ = lim.try_acquire(3, owner="a", max_per_owner=1)
    first.release()
    second, _ = lim.try_acquire(3, owner="a", max_per_owner=1)
    assert second is not None
    first.release()  # stale handle: must not free the new slot
    assert lim.try_acquire(3, owner="a", max_per_owner=1) == (None, "owner")
    second.release()
    assert lim.try_acquire(3, owner="a", max_per_owner=1)[0] is not None


def test_expired_lease_and_max_duration_free_the_owner_too():
    clock = FakeClock()
    lim = StreamLimiter(clock=clock, lease_seconds=10, max_stream_seconds=30)
    lim.try_acquire(3, owner="a", max_per_owner=1)
    assert lim.try_acquire(3, owner="a", max_per_owner=1)[1] == "owner"
    clock.now = 11  # idle lease passed: the dead stream no longer pins the owner
    slot, _ = lim.try_acquire(3, owner="a", max_per_owner=1)
    assert slot is not None
    clock.now = 20
    assert slot.renew()
    clock.now = 45  # over the absolute maximum: renew fails and the owner is freed
    assert slot.renew() is False
    assert lim.try_acquire(3, owner="a", max_per_owner=1)[0] is not None


def test_owner_accounting_is_exact_under_thread_contention():
    lim = StreamLimiter()
    results, lock = [], threading.Lock()

    def worker(owner):
        for _ in range(200):
            slot, _ = lim.try_acquire(30, owner=owner, max_per_owner=1)
            if slot is not None:
                with lock:
                    results.append(owner)
                time.sleep(0)
                slot.release()
                with lock:
                    results.remove(owner)

    threads = [threading.Thread(target=worker, args=(f"u{i % 4}",)) for i in range(16)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert lim.active() == 0 and lim._owners == {}


def test_owner_is_freed_when_a_streaming_generator_is_cancelled(env, monkeypatch):
    db = env.Session()
    user = db.get(User, env.user_id)
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", chunks_then("a", "b"))
    reservation = quota.reserve(db, env.user_id, 6500)
    slot, _ = stream_limiter.try_acquire(3, owner=env.user_id, max_per_owner=1)
    gen = ai_routes.generate_stream(db, user, ChatRequest(message="hi"), None, [], [], {}, slot, reservation)
    next(gen)
    assert stream_limiter.try_acquire(3, owner=env.user_id, max_per_owner=1) == (None, "owner")
    gen.close()  # client went away
    slot2, _ = stream_limiter.try_acquire(3, owner=env.user_id, max_per_owner=1)
    assert slot2 is not None
    slot2.release()
    assert stream_limiter.active() == 0
