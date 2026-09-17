"""登录失败限制接口行为：429 与剩余分钟、成功清零、代理头信任边界。"""

from fastapi.testclient import TestClient

from invoice_sorting.auth.ratelimit import LoginRateLimiter
from tests.auth_helpers import PASSWORD, setup_password
from tests.unit.test_auth_ratelimit import FakeClock


def install_clock(app) -> FakeClock:
    clock = FakeClock()
    app.state.login_limiter = LoginRateLimiter(clock=clock)
    return clock


def fail(client, times: int, headers: dict | None = None) -> None:
    for _ in range(times):
        response = client.post(
            "/api/auth/login", json={"password": "wrong-password"}, headers=headers
        )
        assert response.status_code == 401


def test_lockout_after_five_failures_and_recovery(auth_app, auth_client):
    clock = install_clock(auth_app)
    setup_password(auth_client)
    auth_client.cookies.clear()
    fail(auth_client, 5)
    response = auth_client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 429
    assert response.json()["error"] == "尝试次数过多，请 15 分钟后再试"

    clock.advance(10 * 60 + 30)
    response = auth_client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.json()["error"] == "尝试次数过多，请 5 分钟后再试"

    clock.advance(5 * 60)
    assert auth_client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200


def test_success_resets_failure_count(auth_app, auth_client):
    install_clock(auth_app)
    setup_password(auth_client)
    fail(auth_client, 4)
    assert auth_client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    fail(auth_client, 4)
    assert auth_client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200


def test_real_ip_trusted_only_from_local_proxy(auth_app, auth_client):
    install_clock(auth_app)
    setup_password(auth_client)
    proxy = TestClient(auth_app, client=("127.0.0.1", 50000))
    fail(proxy, 5, headers={"X-Real-IP": "198.51.100.1"})
    other_user = {"X-Real-IP": "198.51.100.2"}
    response = proxy.post("/api/auth/login", json={"password": PASSWORD}, headers=other_user)
    assert response.status_code == 200
    locked_user = {"X-Real-IP": "198.51.100.1"}
    response = proxy.post("/api/auth/login", json={"password": PASSWORD}, headers=locked_user)
    assert response.status_code == 429

    remote = TestClient(auth_app, client=("203.0.113.5", 50000))
    fail(remote, 5, headers={"X-Real-IP": "198.51.100.3"})
    spoofed = {"X-Real-IP": "198.51.100.4"}
    response = remote.post("/api/auth/login", json={"password": PASSWORD}, headers=spoofed)
    assert response.status_code == 429
