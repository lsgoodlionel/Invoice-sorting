"""附件 API：待归属列表、文件流、缩略图、修改、删除。"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from invoice_sorting.attachments.serializers import serialize_attachment
from invoice_sorting.attachments.service import (
    delete_attachment,
    get_attachment_or_404,
    list_unassigned,
    update_attachment,
)
from invoice_sorting.attachments.storage import absolute_path
from invoice_sorting.attachments.thumbnails import get_thumbnail
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import NotFoundError, ok
from invoice_sorting.settings.deps import ConfigDep, SessionDep
from invoice_sorting.settings.service import buyer_identity

router = APIRouter(prefix="/api", tags=["附件"])


class AttachmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AttachmentKind | None = None
    expense_id: int | None = None


@router.get("/attachments/unassigned")
def unassigned(session: SessionDep) -> dict[str, Any]:
    buyer = buyer_identity(session)
    return ok([serialize_attachment(item, buyer) for item in list_unassigned(session)])


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
    return ok(serialize_attachment(attachment, buyer_identity(session)))


@router.delete("/attachments/{attachment_id}")
def remove_attachment(attachment_id: int, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    delete_attachment(session, config, get_attachment_or_404(session, attachment_id))
    session.commit()
    return ok(None)
