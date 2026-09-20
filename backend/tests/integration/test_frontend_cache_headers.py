"""升级后不能让浏览器继续用旧的 index.html 去取已删除的分片（页面会卡在加载中）。"""

from fastapi.testclient import TestClient

from invoice_sorting.main import ASSET_CACHE_CONTROL, INDEX_CACHE_CONTROL, create_app
from tests.conftest import make_settings


def build_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<script src="/assets/index-abc123.js"></script>', "utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", "utf-8")
    return dist


def make_client(tmp_path) -> TestClient:
    settings = make_settings(tmp_path, frontend_dist=build_dist(tmp_path))
    return TestClient(create_app(settings))


def test_index_is_revalidated_every_time(tmp_path):
    client = make_client(tmp_path)

    for path in ("/", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == INDEX_CACHE_CONTROL, path


def test_hashed_assets_are_cached_long_term(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == ASSET_CACHE_CONTROL


def test_missing_asset_is_not_served_as_index(tmp_path):
    """旧分片已被删除时必须 404，而不是回落到 index.html（否则浏览器把 HTML 当 JS 解析）。"""
    client = make_client(tmp_path)

    assert client.get("/assets/index-old999.js").status_code == 404
