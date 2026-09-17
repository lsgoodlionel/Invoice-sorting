"""分文件导入并发：同一文件并发上传两次只入库一次，其余文件正常导入，不出现 500。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from invoice_sorting.attachments import evidence_records
from invoice_sorting.db.models import Attachment
from invoice_sorting.importer import service as importer_service
from tests.evidence_factory import png
from tests.integration.test_import_files_api import finish, start

BARRIER_TIMEOUT_SECONDS = 5


def post_file(client, session_id: str, path: Path, name: str) -> tuple[int, dict]:
    files = {"file": (name, path.read_bytes(), "image/png")}
    response = client.post(f"/api/imports/{session_id}/files", files=files)
    return response.status_code, response.json()


def test_same_file_uploaded_concurrently_is_imported_once(
    client, tmp_path, monkeypatch, fake_recognition
):
    same = png(tmp_path, "same.png")
    others = [png(tmp_path, f"other-{index}.png") for index in range(4)]
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    original = fake_recognition.recognize

    def recognize(path: Path, name: str):
        if name.startswith("same"):
            barrier.wait()  # 两次上传都通过只读预检后再同时写库
        return original(path, name)

    monkeypatch.setattr(evidence_records, "recognize_evidence", recognize)
    session_id = start(client)
    jobs = [(same, "same-a.png"), (same, "same-b.png")] + [(p, p.name) for p in others]

    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda job: post_file(client, session_id, *job), jobs))

    assert all(code == 200 for code, _body in responses), responses
    statuses = {body["data"]["original_name"]: body["data"]["status"] for _c, body in responses}
    same_statuses = sorted(statuses.pop(name) for name in ("same-a.png", "same-b.png"))
    assert same_statuses == ["duplicate", "imported"]
    assert set(statuses.values()) == {"imported"}
    data = finish(client, session_id)
    assert len(data["groups"]) == 5 and len(data["duplicates"]) == 1
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count(Attachment.id))) == 5
    unassigned = client.app.state.settings.library_dir / "待归属"
    assert len(list(unassigned.iterdir())) == 5


def _raise_integrity(*_args, **_kwargs):
    raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))


def test_integrity_error_on_insert_returns_duplicate(client, tmp_path, monkeypatch):
    monkeypatch.setattr(importer_service, "store_file", _raise_integrity)
    session_id = start(client)

    code, body = post_file(client, session_id, png(tmp_path, "a.png"), "a.png")

    assert code == 200
    assert body["data"]["status"] == "duplicate" and body["data"]["message"] == "文件已导入"
    assert finish(client, session_id)["duplicates"][0]["original_name"] == "a.png"


def test_integrity_error_after_copy_rolls_back_and_removes_file(
    client, tmp_path, monkeypatch, fake_recognition
):
    monkeypatch.setattr(importer_service, "relocate_attachment", _raise_integrity)
    session_id = start(client)

    code, body = post_file(client, session_id, png(tmp_path, "b.png"), "b.png")

    assert code == 200 and body["data"]["status"] == "duplicate"
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count(Attachment.id))) == 0
    unassigned = client.app.state.settings.library_dir / "待归属"
    assert not unassigned.exists() or list(unassigned.iterdir()) == []


def test_other_database_error_returns_error_status(client, tmp_path, monkeypatch, fake_recognition):
    from sqlalchemy.exc import OperationalError

    def locked(*_args, **_kwargs):
        raise OperationalError("UPDATE", {}, Exception("database is locked"))

    monkeypatch.setattr(importer_service, "relocate_attachment", locked)
    session_id = start(client)

    code, body = post_file(client, session_id, png(tmp_path, "c.png"), "c.png")

    assert code == 200 and body["data"]["status"] == "error"
    assert body["data"]["message"] == importer_service.UNEXPECTED_ERROR


def test_commit_failure_rolls_back_and_removes_file(session, settings, tmp_path, fake_recognition):
    from invoice_sorting.importer.file_import import import_and_commit

    def failing_commit():
        raise IntegrityError("COMMIT", {}, Exception("UNIQUE constraint failed"))

    session.commit = failing_commit
    outcome = import_and_commit(session, settings, png(tmp_path, "d.png"), "d.png")

    assert outcome.status == "duplicate" and outcome.attachment is None
    assert list((settings.library_dir / "待归属").iterdir()) == []


def test_parser_crash_returns_error_without_storing(client, tmp_path, monkeypatch):
    def crash(_path):
        raise RuntimeError("boom")

    monkeypatch.setattr(importer_service, "parse_invoice_file", crash)
    session_id = start(client)

    code, body = post_file(client, session_id, png(tmp_path, "e.png"), "e.png")

    assert code == 200 and body["data"]["status"] == "error"
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count(Attachment.id))) == 0
