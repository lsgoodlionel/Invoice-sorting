"""测试公共夹具：每个测试使用独立的临时数据目录。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        open_browser=False,
        watch_inbox=False,
        frontend_dist=tmp_path / "no-frontend",
    )


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


FIXTURES_DIR = Path(__file__).parent / "fixtures"
