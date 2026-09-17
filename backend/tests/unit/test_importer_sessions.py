"""导入会话内存存储：过期、容量上限、移除已处理附件。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

from invoice_sorting.importer.sessions import ImportSessionStore, get_session_store


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def test_put_and_get_attachment_ids():
    store = ImportSessionStore()

    session_id = store.create([1, 2, 2])

    assert store.get(session_id) == frozenset({1, 2})
    assert store.get("missing") is None


def test_sessions_expire_after_ttl():
    clock = FakeClock()
    store = ImportSessionStore(ttl_seconds=10, clock=clock)
    session_id = store.create([1])

    clock.value += 11

    assert store.get(session_id) is None


def test_keeps_at_most_max_sessions():
    store = ImportSessionStore(max_sessions=2)
    first = store.create([1])
    second = store.create([2])
    third = store.create([3])

    assert store.get(first) is None
    assert store.get(second) == {2}
    assert store.get(third) == {3}


def test_remove_attachments_drops_empty_session():
    store = ImportSessionStore()
    session_id = store.create([1, 2])

    store.remove_attachments(session_id, [1])
    assert store.get(session_id) == {2}

    store.remove_attachments(session_id, [2, 99])
    assert store.get(session_id) is None
    store.remove_attachments("missing", [1])


def test_get_returns_immutable_set():
    store = ImportSessionStore()
    session_id = store.create([1])

    assert isinstance(store.get(session_id), frozenset)


def test_store_is_attached_to_app_state_once():
    app = SimpleNamespace(state=SimpleNamespace())

    store = get_session_store(app)

    assert get_session_store(app) is store
    assert app.state.import_sessions is store


def test_start_creates_empty_session_snapshot():
    store = ImportSessionStore()

    session_id = store.start()

    snapshot = store.snapshot(session_id)
    assert snapshot is not None
    assert snapshot.attachment_ids == frozenset()
    assert (snapshot.duplicates, snapshot.errors, snapshot.notices) == ((), (), ())
    assert store.get(session_id) == frozenset()
    assert store.snapshot("missing") is None


def test_add_file_outcome_accumulates_records():
    store = ImportSessionStore()
    session_id = store.start()
    june = date(2026, 6, 1)

    assert store.add_file_outcome(
        session_id, attachment_id=1, warnings=["外地发票"], occurred_on=june
    )
    store.add_file_outcome(
        session_id, attachment_id=2, notice={"original_name": "b", "message": "m"}
    )
    store.add_file_outcome(session_id, duplicate={"original_name": "c", "reason": "r"})
    store.add_file_outcome(session_id, error={"original_name": "d", "error": "e"})

    snapshot = store.snapshot(session_id)
    assert snapshot.attachment_ids == {1, 2}
    assert snapshot.warnings == {1: ("外地发票",), 2: ()}
    assert snapshot.occurred_on == {1: june}
    assert snapshot.notices == ({"original_name": "b", "message": "m"},)
    assert snapshot.duplicates == ({"original_name": "c", "reason": "r"},)
    assert snapshot.errors == ({"original_name": "d", "error": "e"},)
    assert store.add_file_outcome("missing", attachment_id=3) is False


def test_remove_attachments_keeps_session_records():
    store = ImportSessionStore()
    session_id = store.start()
    store.add_file_outcome(session_id, attachment_id=1, warnings=["w"])
    store.add_file_outcome(session_id, attachment_id=2, error={"original_name": "x", "error": "e"})

    store.remove_attachments(session_id, [1])

    snapshot = store.snapshot(session_id)
    assert snapshot.attachment_ids == {2}
    assert snapshot.warnings == {2: ()}
    assert len(snapshot.errors) == 1


def test_concurrent_outcomes_are_not_lost():
    store = ImportSessionStore()
    session_id = store.start()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: store.add_file_outcome(session_id, attachment_id=i), range(200)))

    assert store.get(session_id) == frozenset(range(200))
