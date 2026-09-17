"""客户端 IP 与 HTTPS 判断：只信任本机反代的转发头。"""

from starlette.requests import Request

from invoice_sorting.auth.http import client_ip, is_secure_request


def make_request(
    host: str | None = "127.0.0.1", scheme: str = "http", headers: dict | None = None
) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "scheme": scheme,
        "method": "GET",
        "path": "/",
        "headers": raw,
        "client": (host, 1234) if host else None,
    }
    return Request(scope)


def test_client_ip_uses_direct_host_when_not_local():
    request = make_request("8.8.8.8", headers={"X-Real-IP": "1.1.1.1"})
    assert client_ip(request) == "8.8.8.8"


def test_client_ip_trusts_real_ip_from_local_proxy():
    assert client_ip(make_request("127.0.0.1", headers={"X-Real-IP": "1.1.1.1"})) == "1.1.1.1"
    assert client_ip(make_request("::1", headers={"X-Real-IP": "2001:db8::1"})) == "2001:db8::1"


def test_client_ip_uses_proxy_appended_forwarded_for():
    """Nginx 追加的真实地址在末尾，前面的值可被客户端伪造。"""
    request = make_request(headers={"X-Forwarded-For": "6.6.6.6, 9.9.9.9"})
    assert client_ip(request) == "9.9.9.9"


def test_client_ip_ignores_invalid_forwarded_values():
    request = make_request(headers={"X-Real-IP": "not-an-ip", "X-Forwarded-For": "bad"})
    assert client_ip(request) == "127.0.0.1"


def test_client_ip_without_client():
    assert client_ip(make_request(None)) == "unknown"


def test_secure_when_scheme_https():
    assert is_secure_request(make_request("8.8.8.8", scheme="https")) is True


def test_secure_forwarded_proto_only_from_local_proxy():
    headers = {"X-Forwarded-Proto": "https"}
    assert is_secure_request(make_request("127.0.0.1", headers=headers)) is True
    assert is_secure_request(make_request("8.8.8.8", headers=headers)) is False
    assert is_secure_request(make_request("127.0.0.1")) is False
