"""导入会话内存存储：过期、容量上限、移除已处理行。"""

from types import SimpleNamespace

from invoice_sorting.importer.sessions import ImportSessionStore, get_session_store


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def test_put_and_get_rows():
    store = ImportSessionStore()

    session_id = store.create({"r1": 1, "r2": 2})

    assert store.get(session_id) == {"r1": 1, "r2": 2}
    assert store.get("missing") is None


def test_sessions_expire_after_ttl():
    clock = FakeClock()
    store = ImportSessionStore(ttl_seconds=10, clock=clock)
    session_id = store.create({"r1": 1})

    clock.value += 11

    assert store.get(session_id) is None


def test_keeps_at_most_max_sessions():
    store = ImportSessionStore(max_sessions=2)
    first = store.create({"a": 1})
    second = store.create({"b": 2})
    third = store.create({"c": 3})

    assert store.get(first) is None
    assert store.get(second) == {"b": 2}
    assert store.get(third) == {"c": 3}


def test_remove_rows_drops_empty_session():
    store = ImportSessionStore()
    session_id = store.create({"a": 1, "b": 2})

    store.remove_rows(session_id, ["a"])
    assert store.get(session_id) == {"b": 2}

    store.remove_rows(session_id, ["b"])
    assert store.get(session_id) is None
    store.remove_rows("missing", ["x"])


def test_get_returns_copy():
    store = ImportSessionStore()
    session_id = store.create({"a": 1})

    store.get(session_id)["b"] = 2

    assert store.get(session_id) == {"a": 1}


def test_store_is_attached_to_app_state_once():
    app = SimpleNamespace(state=SimpleNamespace())

    store = get_session_store(app)

    assert get_session_store(app) is store
    assert app.state.import_sessions is store
