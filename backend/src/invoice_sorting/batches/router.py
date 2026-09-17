"""报销批次 API：批次 CRUD、加入/移出记录、外发、到账、撤销与资料包导出。"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from invoice_sorting.batches.items import change_items
from invoice_sorting.batches.lifecycle import mark_received, mark_sent, reopen_batch
from invoice_sorting.batches.schemas import (
    BatchCreate,
    BatchItems,
    BatchReceived,
    BatchSent,
    BatchUpdate,
    ExportRequest,
)
from invoice_sorting.batches.serializers import (
    serialize_batch,
    serialize_batch_detail,
    serialize_export_record,
)
from invoice_sorting.batches.service import (
    create_batch,
    delete_batch,
    get_batch_or_404,
    list_batches,
    reload_batch,
    update_batch,
)
from invoice_sorting.common.constants import BatchStatus
from invoice_sorting.common.errors import NotFoundError, ok
from invoice_sorting.db.models import ExportRecord
from invoice_sorting.exporter.package import delete_export, export_batch
from invoice_sorting.settings.deps import ConfigDep, SessionDep

router = APIRouter(prefix="/api", tags=["报销批次"])

ZIP_MIME = "application/zip"


@router.get("/batches")
def get_batches(session: SessionDep, status: BatchStatus | None = None) -> dict[str, Any]:
    return ok([serialize_batch(batch) for batch in list_batches(session, status)])


@router.post("/batches")
def post_batch(body: BatchCreate, session: SessionDep) -> dict[str, Any]:
    batch = create_batch(session, name=body.name, project_id=body.project_id, note=body.note)
    session.commit()
    return ok(serialize_batch_detail(batch))


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, session: SessionDep) -> dict[str, Any]:
    batch = reload_batch(session, get_batch_or_404(session, batch_id))
    return ok(serialize_batch_detail(batch))


@router.patch("/batches/{batch_id}")
def patch_batch(batch_id: int, body: BatchUpdate, session: SessionDep) -> dict[str, Any]:
    batch = update_batch(session, get_batch_or_404(session, batch_id), body.changes())
    session.commit()
    return ok(serialize_batch_detail(batch))


@router.delete("/batches/{batch_id}")
def remove_batch(batch_id: int, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    delete_batch(session, config, get_batch_or_404(session, batch_id))
    session.commit()
    return ok(None)


@router.post("/batches/{batch_id}/items")
def post_items(
    batch_id: int, body: BatchItems, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    batch = get_batch_or_404(session, batch_id)
    change_items(session, config, batch, add=body.add, remove=body.remove, force=body.force)
    session.commit()
    return ok(serialize_batch_detail(batch))


@router.post("/batches/{batch_id}/sent")
def post_sent(
    batch_id: int, body: BatchSent, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    batch = mark_sent(session, config, get_batch_or_404(session, batch_id), **body.model_dump())
    session.commit()
    return ok(serialize_batch_detail(batch))


@router.post("/batches/{batch_id}/received")
def post_received(
    batch_id: int, body: BatchReceived, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    batch = get_batch_or_404(session, batch_id)
    mark_received(
        session, config, batch, received_on=body.received_on, expense_ids=body.expense_ids
    )
    session.commit()
    return ok(serialize_batch_detail(batch))


@router.post("/batches/{batch_id}/reopen")
def post_reopen(batch_id: int, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    batch = reopen_batch(session, config, get_batch_or_404(session, batch_id))
    session.commit()
    return ok(serialize_batch_detail(batch))


@router.post("/batches/{batch_id}/export")
def post_export(
    batch_id: int, body: ExportRequest, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    record = export_batch(session, config, get_batch_or_404(session, batch_id), body.layout)
    session.commit()
    return ok(serialize_export_record(record))


@router.get("/exports/{export_id}/file")
def get_export_file(export_id: int, session: SessionDep, config: ConfigDep) -> FileResponse:
    record = session.get(ExportRecord, export_id)
    if record is None:
        raise NotFoundError("导出记录")
    path = config.data_dir / record.file_path
    if not path.is_file():
        raise NotFoundError("资料包文件")
    return FileResponse(path, media_type=ZIP_MIME, filename=path.name)


@router.delete("/exports/{export_id}")
def remove_export(export_id: int, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    record = session.get(ExportRecord, export_id)
    if record is None:
        raise NotFoundError("导出记录")
    delete_export(session, config, record)
    session.commit()
    return ok(None)
