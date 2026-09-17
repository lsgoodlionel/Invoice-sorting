"""导入 API：批量导入文件并按凭证组生成确认会话，确认后建记录或挂到已有记录。"""

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Request, UploadFile

from invoice_sorting.attachments.uploads import save_upload, upload_name
from invoice_sorting.common.errors import AppError, NotFoundError, ok
from invoice_sorting.importer.confirm import confirm_groups
from invoice_sorting.importer.schemas import ConfirmRequest
from invoice_sorting.importer.serializers import serialize_import
from invoice_sorting.importer.service import ImportResult, import_files
from invoice_sorting.importer.sessions import get_session_store
from invoice_sorting.settings.deps import ConfigDep, SessionDep
from invoice_sorting.settings.service import buyer_identity, region_policy

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


@router.post("/imports")
def post_import(
    request: Request,
    session: SessionDep,
    config: ConfigDep,
    files: Annotated[list[UploadFile], File()],
) -> dict[str, Any]:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=config.data_dir, prefix=".import-") as tmp:
        saved, failures = _save_uploads(files, Path(tmp))
        result = import_files(session, config, saved) if saved else ImportResult()
        session.commit()
    for name, message in failures:
        result.add_error(name, message)
    session_id = get_session_store(request.app).create(result.attachment_ids)
    return ok(serialize_import(session_id, result, buyer_identity(session), region_policy(session)))


@router.post("/imports/{session_id}/confirm")
def post_confirm(
    session_id: str,
    body: ConfirmRequest,
    request: Request,
    session: SessionDep,
    config: ConfigDep,
) -> dict[str, Any]:
    store = get_session_store(request.app)
    allowed = store.get(session_id)
    if allowed is None:
        raise ImportSessionExpiredError()
    result = confirm_groups(session, config, set(allowed), body.groups)
    session.commit()
    store.remove_attachments(session_id, {i for group in body.groups for i in group.attachment_ids})
    return ok(result.as_dict())
