"""导入 API：批量或分文件（start → files → finish）导入并按凭证组生成确认会话，确认后建记录。"""

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Request, UploadFile
from sqlalchemy.orm import Session

from invoice_sorting.attachments.uploads import save_upload, upload_name
from invoice_sorting.common.errors import AppError, NotFoundError, ok
from invoice_sorting.config import Settings
from invoice_sorting.importer.confirm import confirm_groups
from invoice_sorting.importer.file_import import (
    finish_session,
    import_and_commit,
    record_outcome,
    serialize_file_outcome,
)
from invoice_sorting.importer.schemas import ConfirmRequest
from invoice_sorting.importer.serializers import serialize_import
from invoice_sorting.importer.service import (
    STATUS_ERROR,
    FileOutcome,
    ImportResult,
    import_files,
)
from invoice_sorting.importer.sessions import ImportSessionStore, get_session_store
from invoice_sorting.settings.deps import ConfigDep, SessionDep, TenantDep
from invoice_sorting.settings.service import buyer_identity, region_policy
from invoice_sorting.tenancy.runtime import TenantContext

router = APIRouter(prefix="/api", tags=["导入"])

SESSION_EXPIRED = "导入会话已过期，请重新导入"
MAX_SUFFIX_CHARS = 6


class ImportSessionExpiredError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("导入会话")
        self.message = SESSION_EXPIRED


def _temp_name(index: int, original_name: str) -> str:
    """保留扩展名，便于解析器按后缀识别票种。"""
    suffix = Path(original_name).suffix.lower()
    if not (1 < len(suffix) <= MAX_SUFFIX_CHARS and suffix[1:].isalnum()):
        suffix = ""
    return f"{index}{suffix}"


def _save_uploads(
    files: list[UploadFile], directory: Path
) -> tuple[list[tuple[Path, str]], list[tuple[str, str]]]:
    saved: list[tuple[Path, str]] = []
    failures: list[tuple[str, str]] = []
    for index, upload in enumerate(files):
        name = upload_name(upload)
        try:
            saved.append((save_upload(upload, directory / _temp_name(index, name)), name))
        except AppError as exc:
            failures.append((name, exc.message))
    return saved, failures


def _store(request: Request, tenant: TenantContext) -> ImportSessionStore:
    """导入会话按租户分区，别的租户拿到 session_id 也查不到附件。"""
    return get_session_store(request.app, tenant.slug)


@router.post("/imports")
def post_import(
    request: Request,
    session: SessionDep,
    config: ConfigDep,
    tenant: TenantDep,
    files: Annotated[list[UploadFile], File()],
) -> dict[str, Any]:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=config.data_dir, prefix=".import-") as tmp:
        saved, failures = _save_uploads(files, Path(tmp))
        result = import_files(session, config, saved) if saved else ImportResult()
        session.commit()
    for name, message in failures:
        result.add_error(name, message)
    session_id = _store(request, tenant).create(result.attachment_ids)
    return ok(serialize_import(session_id, result, buyer_identity(session), region_policy(session)))


@router.post("/imports/start")
def post_import_start(request: Request, tenant: TenantDep) -> dict[str, Any]:
    return ok({"session_id": _store(request, tenant).start()})


def _live_store(request: Request, tenant: TenantContext, session_id: str) -> ImportSessionStore:
    store = _store(request, tenant)
    if store.get(session_id) is None:
        raise ImportSessionExpiredError()
    return store


def _import_upload(session: Session, config: Settings, upload: UploadFile) -> FileOutcome:
    """上传保存失败（类型不支持、过大）也作为 error 结论返回，便于前端逐文件显示。"""
    name = upload_name(upload)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=config.data_dir, prefix=".import-") as tmp:
        try:
            src = save_upload(upload, Path(tmp) / _temp_name(0, name))
        except AppError as exc:
            return FileOutcome(name, STATUS_ERROR, message=exc.message)
        return import_and_commit(session, config, src, name)


@router.post("/imports/{session_id}/files")
def post_import_file(
    session_id: str,
    request: Request,
    session: SessionDep,
    config: ConfigDep,
    tenant: TenantDep,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    store = _live_store(request, tenant, session_id)
    outcome = _import_upload(session, config, file)
    record_outcome(store, session_id, outcome)
    return ok(serialize_file_outcome(outcome, buyer_identity(session), region_policy(session)))


@router.post("/imports/{session_id}/finish")
def post_import_finish(
    session_id: str, request: Request, session: SessionDep, tenant: TenantDep
) -> dict[str, Any]:
    snapshot = _store(request, tenant).snapshot(session_id)
    if snapshot is None:
        raise ImportSessionExpiredError()
    result = finish_session(session, snapshot)
    return ok(serialize_import(session_id, result, buyer_identity(session), region_policy(session)))


@router.post("/imports/{session_id}/confirm")
def post_confirm(
    session_id: str,
    body: ConfirmRequest,
    request: Request,
    session: SessionDep,
    config: ConfigDep,
    tenant: TenantDep,
) -> dict[str, Any]:
    store = _store(request, tenant)
    allowed = store.get(session_id)
    if allowed is None:
        raise ImportSessionExpiredError()
    result = confirm_groups(session, config, set(allowed), body.groups)
    session.commit()
    store.remove_attachments(session_id, {i for group in body.groups for i in group.attachment_ids})
    return ok(result.as_dict())
