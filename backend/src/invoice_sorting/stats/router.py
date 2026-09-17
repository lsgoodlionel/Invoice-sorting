"""统计与首页提醒 API。"""

from datetime import date, datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from invoice_sorting.common.constants import DateBasis
from invoice_sorting.common.errors import ok
from invoice_sorting.db.models import TZ
from invoice_sorting.settings.deps import SessionDep
from invoice_sorting.stats.dashboard import build_dashboard
from invoice_sorting.stats.service import (
    StatsGroupBy,
    StatsQuery,
    load_entries,
    summarize,
    validate_range,
)
from invoice_sorting.stats.workbook import build_stats_workbook

router = APIRouter(prefix="/api", tags=["统计"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_today() -> date:
    """当前日期（Asia/Shanghai）。测试可通过 app.dependency_overrides 注入。"""
    return datetime.now(TZ).date()


def stats_query(
    start: date,
    end: date,
    date_basis: DateBasis = DateBasis.SPENT,
    group_by: StatsGroupBy = StatsGroupBy.CATEGORY,
) -> StatsQuery:
    query = StatsQuery(start=start, end=end, date_basis=date_basis, group_by=group_by)
    validate_range(query)
    return query


StatsQueryDep = Annotated[StatsQuery, Depends(stats_query)]
TodayDep = Annotated[date, Depends(get_today)]


def content_disposition(filename: str) -> str:
    """RFC 5987：ASCII 兜底名 + UTF-8 编码的真实文件名。"""
    return f"attachment; filename=\"stats.xlsx\"; filename*=UTF-8''{quote(filename)}"


@router.get("/stats")
def get_stats(session: SessionDep, query: StatsQueryDep) -> dict[str, Any]:
    return ok(summarize(query, load_entries(session, query)))


@router.get("/stats/export")
def export_stats(session: SessionDep, query: StatsQueryDep) -> Response:
    entries = load_entries(session, query)
    content = build_stats_workbook(query, summarize(query, entries), entries)
    filename = f"统计_{query.start}_{query.end}.xlsx"
    headers = {"Content-Disposition": content_disposition(filename)}
    return Response(content=content, media_type=XLSX_MIME, headers=headers)


@router.get("/dashboard")
def get_dashboard(session: SessionDep, today: TodayDep) -> dict[str, Any]:
    return ok(build_dashboard(session, today))
