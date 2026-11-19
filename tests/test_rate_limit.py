"""Login/registration rate limiting, client-address resolution and enumeration resistance."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.auth.hash import hash_password
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models.user import User
from src.security import rate_limit
from src.security.rate_limit import SlidingWindowLimiter, get_client_ip
from src.services import auth_service

USERNAME = "demo_user"
EMAIL = "demo@example.com"
PASSWORD = "CorrectHorseBattery1!"
WRONG_PASSWORD = "definitely-the-wrong-password"
GENERIC_401 = "Invalid username/email or password"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# ------------------------------------------------------------------ limiter unit
def test_limiter_allows_up_to_the_limit_then_blocks_with_retry_after():
    clock = FakeClock()
    lim = SlidingWindowLimiter(clock=clock)
    for _ in range(3):
        assert lim.hit("k", 3) == (True, 0)
    allowed, retry_after = lim.hit("k", 3)
    assert allowed is False
    assert 1 <= retry_after <= 60


def test_limiter_retry_after_counts_down_and_window_releases():
    clock = FakeClock()
    lim = SlidingWindowLimiter(clock=clock)
    for _ in range(2):
        lim.hit("k", 2)
    clock.advance(20)
    assert lim.hit("k", 2) == (False, 40)
    clock.advance(40)
    assert lim.hit("k", 2) == (True, 0)


def test_rejected_hits_do_not_extend_the_block():
    clock = FakeClock()
    lim = SlidingWindowLimiter(clock=clock)
    lim.hit("k", 1)
    for _ in range(10):
        clock.advance(5)
        assert lim.hit("k", 1)[0] is False
    clock.advance(10)  # 60 s after the only recorded hit
    assert lim.hit("k", 1)[0] is True


def test_limiter_keys_are_independent():
    lim = SlidingWindowLimiter(clock=FakeClock())
    lim.hit("a", 1)
    assert lim.hit("a", 1)[0] is False
    assert lim.hit("b", 1)[0] is True


def test_limiter_memory_is_bounded_and_evicts_least_recently_used():
    lim = SlidingWindowLimiter(clock=FakeClock(), max_keys=3)
    for key in ("a", "b", "c", "d"):
        lim.hit(key, 5)
    assert len(lim.tracked_keys()) == 3
    assert "a" not in lim.tracked_keys()


# ------------------------------------------------------------ client address
def fake_request(peer="203.0.113.5", xff=None):
    from starlette.datastructures import Headers

    values = [] if xff is None else ([xff] if isinstance(xff, str) else list(xff))
    headers = Headers(raw=[(b"x-forwarded-for", v.encode()) for v in values])
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_forwarded_header_is_ignored_by_default(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    assert get_client_ip(fake_request(xff="198.51.100.7")) == "203.0.113.5"


def test_trusted_proxy_uses_entry_written_by_own_proxy_not_client_supplied_ones(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    # The client forged the left entries; the proxy appended the real address on the right.
    assert get_client_ip(fake_request(xff="6.6.6.6, 7.7.7.7, 198.51.100.7")) == "198.51.100.7"


def test_two_trusted_proxies_take_the_second_from_the_right(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 2)
    assert get_client_ip(fake_request(xff="6.6.6.6, 198.51.100.7, 10.0.0.1")) == "198.51.100.7"


@pytest.mark.parametrize("xff", [None, "", "198.51.100.7", "not-an-ip, also-bad"])
def test_short_or_malformed_header_falls_back_to_the_peer(monkeypatch, xff):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 2)
    assert get_client_ip(fake_request(xff=xff)) == "203.0.113.5"


@pytest.mark.parametrize("xff", [
    "1.2.3.4:5555",              # port attached: not a bare address
    "1.2.3.4, unknown",          # proxy wrote a token, not an address
    "1.2.3.4, 999.1.1.1",
    "1.2.3.4, <script>",
    "1.2.3.4, " + "9" * 5000,    # oversized junk
    "1.2.3.4, 10.0.0.1/8",
])
def test_garbage_in_the_trusted_position_falls_back_to_the_peer(monkeypatch, xff):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    assert get_client_ip(fake_request(xff=xff)) == "203.0.113.5"


def test_repeated_forwarded_header_lines_are_treated_as_one_list(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    # A client-sent line followed by the line the proxy appended.
    assert get_client_ip(fake_request(xff=["6.6.6.6", "198.51.100.7"])) == "198.51.100.7"
    # A forged extra line can only change entries to the LEFT of the trusted one.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 2)
    assert get_client_ip(fake_request(xff=["6.6.6.6, 198.51.100.7", "10.0.0.1"])) == "198.51.100.7"


def test_ipv4_mapped_ipv6_peer_and_plain_ipv4_share_one_bucket(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    assert get_client_ip(fake_request(peer="::ffff:203.0.113.5")) == get_client_ip(fake_request(peer="203.0.113.5"))


def test_spoofed_left_entries_cannot_rotate_the_limiter_key(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    keys = {get_client_ip(fake_request(xff=f"9.9.9.{i}, 198.51.100.7")) for i in range(50)}
    assert keys == {"198.51.100.7"}


def test_ipv6_clients_share_one_bucket_per_64(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    a = get_client_ip(fake_request(peer="2001:db8:1:2::1"))
    b = get_client_ip(fake_request(peer="2001:db8:1:2:ffff::9"))
    c = get_client_ip(fake_request(peer="2001:db8:1:3::1"))
    assert a == b != c


# -------------------------------------------------------------- HTTP behaviour
@pytest.fixture
def auth_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = Session()
    db.add(User(username=USERNAME, email=EMAIL, hashed_password=hash_password(PASSWORD)))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def client_from(ip):
    return TestClient(app, client=(ip, 50000))


def login(client, username=USERNAME, password=PASSWORD, **headers):
    return client.post("/auth/login", data={"username": username, "password": password}, headers=headers)


def test_normal_login_still_works(auth_env):
    response = login(client_from("203.0.113.10"))
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert "Retry-After" not in response.headers


def test_failed_attempts_hit_the_threshold_then_get_429_with_retry_after(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    client = client_from("203.0.113.11")
    for _ in range(3):
        assert login(client, password=WRONG_PASSWORD).status_code == 401
    blocked = login(client, password=WRONG_PASSWORD)
    assert blocked.status_code == 429
    retry_after = int(blocked.headers["Retry-After"])
    assert 1 <= retry_after <= 60
    assert blocked.json()["detail"] == rate_limit.RATE_LIMIT_DETAIL


def test_a_correct_password_is_also_blocked_once_the_limit_is_hit(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    client = client_from("203.0.113.12")
    for _ in range(2):
        login(client, password=WRONG_PASSWORD)
    assert login(client).status_code == 429


def test_legitimate_login_works_again_after_the_window(auth_env, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(rate_limit, "limiter", SlidingWindowLimiter(clock=clock))
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    client = client_from("203.0.113.13")
    for _ in range(2):
        login(client, password=WRONG_PASSWORD)
    blocked = login(client)
    assert blocked.status_code == 429
    clock.advance(int(blocked.headers["Retry-After"]))
    assert login(client).status_code == 200


def test_different_client_sources_have_separate_limits(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    attacker, legitimate = client_from("203.0.113.20"), client_from("203.0.113.21")
    for _ in range(2):
        login(attacker, password=WRONG_PASSWORD)
    assert login(attacker).status_code == 429
    assert login(legitimate).status_code == 200


def test_forged_forwarded_header_cannot_dodge_the_limit_by_default(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    client = client_from("203.0.113.30")
    statuses = [login(client, password=WRONG_PASSWORD, **{"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(5)]
    assert statuses == [401, 401, 401, 429, 429]


def test_behind_one_trusted_proxy_the_real_client_is_limited_not_the_proxy(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    proxy = client_from("10.0.0.1")
    for forged in ("1.1.1.1", "2.2.2.2"):  # client-controlled left entries change, real client does not
        login(proxy, password=WRONG_PASSWORD, **{"X-Forwarded-For": f"{forged}, 198.51.100.50"})
    assert login(proxy, **{"X-Forwarded-For": "3.3.3.3, 198.51.100.50"}).status_code == 429
    # A different real client behind the same proxy is unaffected.
    assert login(proxy, **{"X-Forwarded-For": "198.51.100.51"}).status_code == 200


def test_unknown_account_and_wrong_password_are_indistinguishable(auth_env):
    unknown = login(client_from("203.0.113.40"), username="nobody_here")
    wrong = login(client_from("203.0.113.41"), password=WRONG_PASSWORD)
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": GENERIC_401}
    assert unknown.headers.get("www-authenticate") == wrong.headers.get("www-authenticate")


def test_limit_response_is_identical_for_existing_and_unknown_accounts(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 1)
    a, b = client_from("203.0.113.42"), client_from("203.0.113.43")
    login(a, username=USERNAME, password=WRONG_PASSWORD)
    login(b, username="nobody_here", password=WRONG_PASSWORD)
    blocked_known = login(a, username=USERNAME, password=WRONG_PASSWORD)
    blocked_unknown = login(b, username="nobody_here", password=WRONG_PASSWORD)
    assert blocked_known.status_code == blocked_unknown.status_code == 429
    assert blocked_known.json() == blocked_unknown.json()
    assert set(blocked_known.headers) == set(blocked_unknown.headers)


def test_rate_limit_keys_and_logs_contain_no_credentials_or_raw_addresses(auth_env, monkeypatch, caplog):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 1)
    client = client_from("203.0.113.44")
    login(client, username=USERNAME, password=WRONG_PASSWORD)
    with caplog.at_level("WARNING"):
        assert login(client, username=USERNAME, password=WRONG_PASSWORD).status_code == 429
    for key in rate_limit.limiter.tracked_keys():
        assert key.startswith("login:")
        assert USERNAME not in key and EMAIL not in key and WRONG_PASSWORD not in key
    assert "rate limit exceeded" in caplog.text
    for secret in (USERNAME, WRONG_PASSWORD, "203.0.113.44"):
        assert secret not in caplog.text


def test_unknown_account_still_spends_password_hashing_time(auth_env, monkeypatch):
    calls = []
    real = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda plain, hashed: calls.append(hashed) or real(plain, hashed))
    assert auth_service.login_user(auth_env, "nobody_here", WRONG_PASSWORD) is None
    assert len(calls) == 1  # a dummy hash was verified, same work as a real account


def test_registration_has_its_own_counter_and_limit(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", True)
    client = client_from("203.0.113.50")
    body = lambda i: {"username": f"new_user_{i}", "email": f"new{i}@example.com", "password": "AnotherLongPassword1!"}
    assert client.post("/auth/register", json=body(1)).status_code == 200
    assert client.post("/auth/register", json=body(2)).status_code == 200
    third = client.post("/auth/register", json=body(3))
    assert third.status_code == 429 and "Retry-After" in third.headers
    assert login(client).status_code == 200  # login counter is separate
