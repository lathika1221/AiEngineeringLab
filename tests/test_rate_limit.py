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
def fake_request(peer="203.0.113.5", xff=None, real_ip=None):
    """Request double. `xff` / `real_ip` are one header line (str) or several (list)."""
    from starlette.datastructures import Headers

    def lines(name, given):
        values = [] if given is None else ([given] if isinstance(given, str) else list(given))
        return [(name, v.encode()) for v in values]

    headers = Headers(raw=lines(b"x-forwarded-for", xff) + lines(b"x-real-ip", real_ip))
    client = None if peer is None else SimpleNamespace(host=peer)
    return SimpleNamespace(client=client, headers=headers)


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


# ------------------------------------------- X-Real-IP mode (Railway, explicit opt-in)
EDGE_PEER = "100.64.0.9"  # stands in for the platform edge's address; never the client's


@pytest.fixture
def real_ip_mode(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "x-real-ip")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)


def test_x_real_ip_is_ignored_unless_explicitly_configured(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    assert get_client_ip(fake_request(peer=EDGE_PEER, real_ip="198.51.100.7")) == EDGE_PEER


def test_valid_x_real_ip_is_used_when_configured(real_ip_mode):
    assert get_client_ip(fake_request(peer=EDGE_PEER, real_ip="198.51.100.7")) == "198.51.100.7"


def test_x_real_ip_value_is_trimmed(real_ip_mode):
    assert get_client_ip(fake_request(peer=EDGE_PEER, real_ip="  198.51.100.7 ")) == "198.51.100.7"


def test_x_real_ip_ipv4_mapped_ipv6_matches_plain_ipv4(real_ip_mode):
    mapped = get_client_ip(fake_request(peer=EDGE_PEER, real_ip="::ffff:198.51.100.7"))
    assert mapped == get_client_ip(fake_request(peer=EDGE_PEER, real_ip="198.51.100.7")) == "198.51.100.7"


def test_x_real_ip_ipv6_is_reduced_to_its_64_prefix(real_ip_mode):
    a = get_client_ip(fake_request(peer=EDGE_PEER, real_ip="2001:db8:1:2::1"))
    b = get_client_ip(fake_request(peer=EDGE_PEER, real_ip="2001:db8:1:2:ffff::9"))
    c = get_client_ip(fake_request(peer=EDGE_PEER, real_ip="2001:db8:1:3::1"))
    assert a == b != c
    assert a == "2001:db8:1:2::"


def test_missing_x_real_ip_falls_back_to_the_peer(real_ip_mode):
    assert get_client_ip(fake_request(peer=EDGE_PEER)) == EDGE_PEER


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "garbage",
        "unknown",
        "198.51.100.7:443",  # address with a port
        "198.51.100.7, 198.51.100.8",  # a list in one header line
        "198.51.100.7 198.51.100.8",
        "[2001:db8::1]",
        "999.1.1.1",
        "198.51.100",
        "198.051.100.007",  # leading zeros are rejected, not reinterpreted
        "0x7f.0.0.1",
        "fe80::1%eth0",  # IPv6 zone id
        "198.51.100.7\x00",
        "1" * 5000,
    ],
)
def test_malformed_x_real_ip_falls_back_to_the_peer(real_ip_mode, value):
    assert get_client_ip(fake_request(peer=EDGE_PEER, real_ip=value)) == EDGE_PEER


def test_repeated_x_real_ip_headers_fall_back_to_the_peer(real_ip_mode):
    # Neither the first nor the last line is picked, even when both are valid.
    assert get_client_ip(fake_request(peer=EDGE_PEER, real_ip=["198.51.100.7", "198.51.100.8"])) == EDGE_PEER
    assert get_client_ip(fake_request(peer=EDGE_PEER, real_ip=["198.51.100.7", "198.51.100.7"])) == EDGE_PEER


def test_x_forwarded_for_is_never_used_in_x_real_ip_mode(real_ip_mode, monkeypatch):
    xff = "6.6.6.6, 198.51.100.9"
    # Valid X-Real-IP wins over any X-Forwarded-For.
    assert get_client_ip(fake_request(peer=EDGE_PEER, xff=xff, real_ip="198.51.100.7")) == "198.51.100.7"
    # Missing, malformed or repeated X-Real-IP never falls through to X-Forwarded-For.
    assert get_client_ip(fake_request(peer=EDGE_PEER, xff=xff)) == EDGE_PEER
    assert get_client_ip(fake_request(peer=EDGE_PEER, xff=xff, real_ip="garbage")) == EDGE_PEER
    assert get_client_ip(fake_request(peer=EDGE_PEER, xff=xff, real_ip=["198.51.100.7", "198.51.100.8"])) == EDGE_PEER
    # The same holds when a proxy count is (non-production) also configured.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    assert get_client_ip(fake_request(peer=EDGE_PEER, xff=xff)) == EDGE_PEER
    assert get_client_ip(fake_request(peer=EDGE_PEER, xff=xff, real_ip="198.51.100.7")) == "198.51.100.7"


def test_forged_x_forwarded_for_cannot_pick_a_bucket_in_x_real_ip_mode(real_ip_mode):
    # A spoof attempt through the other headers has no effect on the key.
    keys = {get_client_ip(fake_request(peer=EDGE_PEER, xff=f"9.9.9.{i}")) for i in range(50)}
    assert keys == {EDGE_PEER}


def test_x_real_ip_mode_with_no_peer_and_a_bad_header_is_unknown(real_ip_mode):
    assert get_client_ip(fake_request(peer=None, real_ip="garbage")) == "unknown"
    assert get_client_ip(fake_request(peer=None)) == "unknown"
    assert get_client_ip(fake_request(peer=None, real_ip="198.51.100.7")) == "198.51.100.7"


def test_existing_x_forwarded_for_behaviour_is_unchanged_when_the_header_setting_is_empty(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    assert get_client_ip(fake_request(peer="10.0.0.1", xff="6.6.6.6, 198.51.100.7", real_ip="1.1.1.1")) == "198.51.100.7"


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


# ------------------------------- HTTP behaviour in X-Real-IP mode (Railway, explicit opt-in)
# The test client plays the platform edge: it is the socket peer and writes X-Real-IP.
# That the real edge overwrites a client-supplied X-Real-IP is the platform's contract and
# cannot be proven here; see docs/DEPLOYMENT.md (Railway) for the architecture it depends on.
def post_login(client, headers, password=WRONG_PASSWORD):
    """Like login(), but `headers` is a list of (name, value) so a header can repeat."""
    return client.post("/auth/login", data={"username": USERNAME, "password": password}, headers=headers)


def test_real_client_is_limited_not_the_edge_in_x_real_ip_mode(auth_env, real_ip_mode, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    edge = client_from("100.64.0.20")
    statuses = [
        login(edge, password=WRONG_PASSWORD, **{"X-Real-IP": "198.51.100.60", "X-Forwarded-For": f"9.9.9.{i}"}).status_code
        for i in range(5)
    ]
    assert statuses == [401, 401, 401, 429, 429]
    # A different real client behind the same edge is unaffected.
    assert login(edge, **{"X-Real-IP": "198.51.100.61"}).status_code == 200


def test_different_x_real_ip_values_have_separate_login_limits(auth_env, real_ip_mode, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    edge = client_from("100.64.0.21")
    for _ in range(2):
        login(edge, password=WRONG_PASSWORD, **{"X-Real-IP": "198.51.100.62"})
    assert login(edge, **{"X-Real-IP": "198.51.100.62"}).status_code == 429
    assert login(edge, **{"X-Real-IP": "198.51.100.63"}).status_code == 200


def test_x_real_ip_is_ignored_when_the_mode_is_off_so_one_bucket_is_shared(auth_env, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    edge = client_from("100.64.0.22")
    statuses = [login(edge, password=WRONG_PASSWORD, **{"X-Real-IP": f"198.51.100.{70 + i}"}).status_code for i in range(5)]
    assert statuses == [401, 401, 401, 429, 429]


def test_missing_malformed_or_repeated_x_real_ip_share_the_peer_bucket(auth_env, real_ip_mode, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    edge = client_from("100.64.0.23")
    attempts = [
        [],  # missing
        [("X-Real-IP", "not-an-ip")],  # malformed
        [("X-Real-IP", "198.51.100.80"), ("X-Real-IP", "198.51.100.81")],  # repeated
    ]
    assert [post_login(edge, headers).status_code for headers in attempts] == [401, 401, 401]
    # All three landed in the edge's own bucket, so the next such request is blocked ...
    assert post_login(edge, [("X-Real-IP", "also-not-an-ip")]).status_code == 429
    # ... while a request with one valid value has its own bucket.
    assert post_login(edge, [("X-Real-IP", "198.51.100.82")], password=PASSWORD).status_code == 200


def test_forged_x_forwarded_for_cannot_dodge_the_limit_in_x_real_ip_mode(auth_env, real_ip_mode, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    edge = client_from("100.64.0.24")
    # No X-Real-IP at all: the forged X-Forwarded-For values must not select separate buckets.
    statuses = [login(edge, password=WRONG_PASSWORD, **{"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(5)]
    assert statuses == [401, 401, 401, 429, 429]


def test_registration_uses_x_real_ip_in_x_real_ip_mode(auth_env, real_ip_mode, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", True)
    edge = client_from("100.64.0.25")
    body = lambda i: {"username": f"edge_user_{i}", "email": f"edge{i}@example.com", "password": "AnotherLongPassword1!"}
    first = {"X-Real-IP": "198.51.100.90"}
    assert edge.post("/auth/register", json=body(1), headers=first).status_code == 200
    assert edge.post("/auth/register", json=body(2), headers=first).status_code == 200
    blocked = edge.post("/auth/register", json=body(3), headers=first)
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers
    # Another real client behind the same edge can still register.
    assert edge.post("/auth/register", json=body(4), headers={"X-Real-IP": "198.51.100.91"}).status_code == 200


def test_x_real_ip_mode_does_not_log_the_raw_client_ip(auth_env, real_ip_mode, monkeypatch, caplog):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 1)
    edge = client_from("100.64.0.26")
    login(edge, password=WRONG_PASSWORD, **{"X-Real-IP": "198.51.100.92"})
    with caplog.at_level("WARNING"):
        assert login(edge, password=WRONG_PASSWORD, **{"X-Real-IP": "198.51.100.92"}).status_code == 429
    keys = rate_limit.limiter.tracked_keys()
    assert keys and all(key.startswith("login:") for key in keys)
    for key in keys:
        assert USERNAME not in key and WRONG_PASSWORD not in key
    assert "rate limit exceeded" in caplog.text
    assert "198.51.100.92" not in caplog.text
