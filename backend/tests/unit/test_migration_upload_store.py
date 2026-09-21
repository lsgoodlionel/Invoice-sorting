"""导入暂存会话：元数据往返、分片大小计算与过期清理的边界。"""

import os
from dataclasses import replace
from datetime import timedelta

import pytest

from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.db.models import now
from invoice_sorting.migration.restore import UNPACK_DIRNAME
from invoice_sorting.migration.upload_files import MSG_INTERRUPTED, sweep_all, sweep_root
from invoice_sorting.migration.upload_store import (
    MAX_PACKAGE_BYTES,
    MIN_PART_BYTES,
    SESSION_FILENAME,
    STATUS_FAILED,
    STATUS_RUNNING,
    UploadSession,
    UploadStore,
    load_session,
    staging_root,
)
from tests.conftest import make_settings

DAY_AND_A_BIT = timedelta(hours=25)


@pytest.fixture
def base(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def store(base) -> UploadStore:
    return UploadStore(base)


def _new(store: UploadStore, size: int = MIN_PART_BYTES * 2 + 5) -> UploadSession:
    return store.create("default", "账本.zip", size, MIN_PART_BYTES, "AB" * 32)


def test_session_round_trips_through_json(store):
    session = _new(store)

    loaded = load_session(store.directory(session))

    assert loaded == session
    assert loaded.sha256 == "ab" * 32


def test_part_layout_gives_short_last_part(store):
    session = _new(store)

    assert session.part_count == 3
    assert [session.part_bytes(i) for i in range(3)] == [MIN_PART_BYTES, MIN_PART_BYTES, 5]


@pytest.mark.parametrize(
    ("size", "part"),
    [(MAX_PACKAGE_BYTES + 1, MIN_PART_BYTES), (100, MIN_PART_BYTES - 1), (100, 65 * 1024 * 1024)],
)
def test_limits_are_enforced(store, size, part):
    with pytest.raises(AppError):
        store.create("default", "a.zip", size, part, "a" * 64)


def test_require_rejects_other_tenant_and_bad_ids(store):
    session = _new(store)

    with pytest.raises(NotFoundError):
        store.require("alpha", session.id)
    with pytest.raises(NotFoundError):
        store.require("default", "../" + session.id[3:])


def test_exclusive_blocks_a_second_holder(store):
    session = _new(store)

    with store.exclusive(session), pytest.raises(ConflictError):
        with store.exclusive(session):
            pass
    with store.exclusive(session):  # 释放后可以再次进入
        pass


def test_sweep_keeps_fresh_and_removes_expired(store, base):
    fresh, stale = _new(store), _new(store)
    store.update(stale, created_at=now() - DAY_AND_A_BIT)

    removed = sweep_root(staging_root(base, "default"), now())

    assert removed == 1
    assert store.directory(fresh).exists() and not store.directory(stale).exists()


def test_sweep_never_touches_running_imports_outside_startup(store, base):
    session = store.update(_new(store), status=STATUS_RUNNING, created_at=now() - DAY_AND_A_BIT)

    sweep_root(staging_root(base, "default"), now())

    assert load_session(store.directory(session)).status == STATUS_RUNNING


def test_startup_marks_interrupted_imports_failed(store, base):
    session = store.update(_new(store), status=STATUS_RUNNING)

    sweep_all(base, now())

    loaded = load_session(store.directory(session))
    assert loaded.status == STATUS_FAILED and loaded.error == MSG_INTERRUPTED


def test_sweep_ignores_non_session_directories(base):
    root = staging_root(base, "default")
    unpack = root / UNPACK_DIRNAME
    unpack.mkdir(parents=True)
    old = (now() - DAY_AND_A_BIT).timestamp()
    os.utime(unpack, (old, old))

    sweep_root(root, now())

    assert unpack.exists()


def test_corrupt_session_is_removed_only_when_old(store, base):
    young, old = _new(store), _new(store)
    for session in (young, old):
        (store.directory(session) / SESSION_FILENAME).write_text("{坏", encoding="utf-8")
    stamp = (now() - DAY_AND_A_BIT).timestamp()
    os.utime(store.directory(old), (stamp, stamp))

    sweep_root(staging_root(base, "default"), now())

    assert store.directory(young).exists() and not store.directory(old).exists()


def test_sweep_all_covers_saas_tenant_directories(tmp_path):
    saas = make_settings(tmp_path, deployment_mode="saas")
    store = UploadStore(saas)
    session = store.create("alpha", "a.zip", 10, MIN_PART_BYTES, "a" * 64)
    store.save(replace(session, created_at=now() - DAY_AND_A_BIT))

    assert sweep_all(saas, now()) == 1
    assert not store.directory(session).exists()
