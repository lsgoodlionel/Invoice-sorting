"""附件 API：待归属列表、批量操作、文件流、缩略图、修改、删除。"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from invoice_sorting.attachments.bulk import bulk_assign, bulk_delete, load_attachments
from invoice_sorting.attachments.reparse import reparse_attachments
from invoice_sorting.attachments.schemas import AttachmentPatch, BulkAssign, BulkIds
from invoice_sorting.attachments.serializers import serialize_attachment
from invoice_sorting.attachments.service import (
    delete_attachment,
    get_attachment_or_404,
    list_unassigned,
    update_attachment,
)
from invoice_sorting.attachments.storage import absolute_path
from invoice_sorting.attachments.thumbnails import get_thumbnail
from invoice_sorting.common.errors import ConflictError, NotFoundError, ok
from invoice_sorting.db.models import Attachment
from invoice_sorting.importer.from_attachments import create_expenses_from_attachments
from invoice_sorting.importer.matching import candidates_for_attachment
from invoice_sorting.importer.serializers import serialize_candidate
from invoice_sorting.settings.deps import ConfigDep, SessionDep
from invoice_sorting.settings.service import buyer_identity, region_policy

router = APIRouter(prefix="/api", tags=["附件"])


def _serialize_all(session: Session, attachments: list[Attachment]) -> list[dict[str, Any]]:
    buyer, policy = buyer_identity(session), region_policy(session)
    return [serialize_attachment(item, buyer, policy) for item in attachments]


@router.get("/attachments/unassigned")
def unassigned(session: SessionDep) -> dict[str, Any]:
    return ok(_serialize_all(session, list_unassigned(session)))


@router.post("/attachments/bulk-delete")
def post_bulk_delete(body: BulkIds, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    deleted = bulk_delete(session, config, body.ids)
    session.commit()
    return ok({"deleted": deleted})


@router.post("/attachments/bulk-assign")
def post_bulk_assign(body: BulkAssign, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    attachments = bulk_assign(session, config, body.ids, body.expense_id, body.kind)
    session.commit()
    return ok(_serialize_all(session, attachments))


@router.post("/attachments/create-expenses")
def post_create_expenses(body: BulkIds, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    attachments = load_attachments(session, body.ids)
    result = create_expenses_from_attachments(session, config, attachments)
    session.commit()
    return ok(result.as_dict())


@router.post("/attachments/reparse")
def post_reparse(body: BulkIds, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    attachments = reparse_attachments(session, config, body.ids)
    session.commit()
    return ok(_serialize_all(session, attachments))


@router.get("/attachments/{attachment_id}/candidates")
def attachment_candidates(attachment_id: int, session: SessionDep) -> dict[str, Any]:
    attachment = get_attachment_or_404(session, attachment_id)
    if attachment.expense_id is not None:
        raise ConflictError(f"附件已归属到记录 #{attachment.expense_id}")
    candidates = candidates_for_attachment(session, attachment)
    return ok([serialize_candidate(candidate) for candidate in candidates])


@router.get("/attachments/{attachment_id}/file")
def attachment_file(attachment_id: int, session: SessionDep, config: ConfigDep) -> FileResponse:
    attachment = get_attachment_or_404(session, attachment_id)
    path = absolute_path(config, attachment)
    if not path.is_file():
        raise NotFoundError("附件文件")
    return FileResponse(
        path,
        media_type=attachment.mime or "application/octet-stream",
        filename=attachment.original_name,
        content_disposition_type="inline",
    )


@router.get("/attachments/{attachment_id}/thumbnail")
def attachment_thumbnail(
    attachment_id: int, session: SessionDep, config: ConfigDep
) -> FileResponse:
    attachment = get_attachment_or_404(session, attachment_id)
    return FileResponse(get_thumbnail(config, attachment), media_type="image/png")


@router.patch("/attachments/{attachment_id}")
def patch_attachment(
    attachment_id: int, body: AttachmentPatch, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    attachment = get_attachment_or_404(session, attachment_id)
    update_attachment(
        session,
        config,
        attachment,
        kind=body.kind,
        change_expense="expense_id" in body.model_fields_set,
        expense_id=body.expense_id,
    )
    session.commit()
    return ok(serialize_attachment(attachment, buyer_identity(session), region_policy(session)))


@router.delete("/attachments/{attachment_id}")
def remove_attachment(attachment_id: int, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    delete_attachment(session, config, get_attachment_or_404(session, attachment_id))
    session.commit()
    return ok(None)
