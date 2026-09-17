"""测试公共夹具：每个测试使用独立的临时数据目录。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.main import create_app


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "data_dir": tmp_path / "data",
        "open_browser": False,
        "watch_inbox": False,
        "frontend_dist": tmp_path / "no-frontend",
        "auth_enabled": False,  # 现有业务测试不带登录；认证测试使用 auth_* 夹具
        **overrides,
    }
    return Settings(**values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(app) -> Iterator[Session]:
    factory = app.state.session_factory
    with factory() as db_session:
        yield db_session


@pytest.fixture
def auth_settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, auth_enabled=True)


@pytest.fixture
def auth_app(auth_settings: Settings):
    return create_app(auth_settings)


@pytest.fixture
def auth_client(auth_app) -> Iterator[TestClient]:
    with TestClient(auth_app) as test_client:
        yield test_client


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake_recognition(monkeypatch):
    """注入可预设的凭证识别结果（默认未识别、文件名键为空），不依赖真实识别器进度。"""
    from tests.evidence_factory import FakeRecognition

    return FakeRecognition().install(monkeypatch)
