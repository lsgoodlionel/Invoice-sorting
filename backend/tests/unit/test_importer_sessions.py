"""导入会话内存存储：过期、容量上限、移除已处理附件。"""

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
