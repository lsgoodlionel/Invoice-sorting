"""支出记录 API。"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile

from invoice_sorting.attachments.uploads import store_uploads
from invoice_sorting.common.constants import AttachmentKind, DateBasis
from invoice_sorting.common.errors import ok
from invoice_sorting.expenses.listing import list_expenses, parse_statuses
from invoice_sorting.expenses.queries import ExpenseFilter
from invoice_sorting.expenses.schemas import ExpenseCreate, ExpenseUpdate, StatusChange
from invoice_sorting.expenses.serializers import serialize_expense_detail
from invoice_sorting.expenses.service import (
    create_expense,
    get_expense_or_404,
    refresh_expense,
    set_status,
    soft_delete_expense,
    update_expense,
)
from invoice_sorting.settings.deps import ConfigDep, SessionDep

router = APIRouter(prefix="/api", tags=["支出记录"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


@router.get("/expenses")
def get_expenses(
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
    date_basis: DateBasis = DateBasis.SPENT,
    category_id: int | None = None,
    project_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    batch_id: int | None = None,
    unbatched: bool = False,
    missing: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    filters = ExpenseFilter(
        start=start,
        end=end,
        date_basis=date_basis,
        category_id=category_id,
        project_id=project_id,
        statuses=parse_statuses(status),
        q=q,
        batch_id=batch_id,
        unbatched=unbatched,
        missing=missing,
    )
    return ok(list_expenses(session, filters, page, page_size))


@router.post("/expenses")
def post_expense(body: ExpenseCreate, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    expense = create_expense(session, config, **body.model_dump())
    session.commit()
    return ok(serialize_expense_detail(session, expense))


@router.get("/expenses/{expense_id}")
def get_expense(expense_id: int, session: SessionDep) -> dict[str, Any]:
    return ok(serialize_expense_detail(session, get_expense_or_404(session, expense_id)))


@router.patch("/expenses/{expense_id}")
def patch_expense(
    expense_id: int, body: ExpenseUpdate, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    expense = get_expense_or_404(session, expense_id)
    update_expense(session, config, expense, **body.changes())
    session.commit()
    return ok(serialize_expense_detail(session, expense))


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    soft_delete_expense(session, config, get_expense_or_404(session, expense_id))
    session.commit()
    return ok(None)


@router.post("/expenses/{expense_id}/status")
def post_status(
    expense_id: int, body: StatusChange, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    expense = get_expense_or_404(session, expense_id)
    set_status(session, config, expense, body.status, body.note)
    session.commit()
    return ok(serialize_expense_detail(session, expense))


@router.post("/expenses/{expense_id}/attachments")
def post_attachments(
    expense_id: int,
    session: SessionDep,
    config: ConfigDep,
    files: Annotated[list[UploadFile], File()],
    kind: Annotated[AttachmentKind | None, Form()] = None,
) -> dict[str, Any]:
    expense = get_expense_or_404(session, expense_id)
    store_uploads(session, config, files, kind, expense)
    refresh_expense(session, config, expense)
    session.commit()
    return ok(serialize_expense_detail(session, expense))
