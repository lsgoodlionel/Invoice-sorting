"""凭证清单规则 API。规则变更在支出记录下次刷新（修改、上传等）时生效。"""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import NotFoundError, ok
from invoice_sorting.db.models import Category, ChecklistRule
from invoice_sorting.settings.deps import SessionDep
from invoice_sorting.settings.schemas import (
    ChecklistRuleCreate,
    ChecklistRuleUpdate,
    present_values,
)
from invoice_sorting.settings.serializers import serialize_rule

router = APIRouter()


def _rule_or_404(session: Session, rule_id: int) -> ChecklistRule:
    rule = session.get(ChecklistRule, rule_id)
    if rule is None:
        raise NotFoundError("清单规则")
    return rule


def _ensure_category(session: Session, category_id: int | None) -> None:
    if category_id is not None and session.get(Category, category_id) is None:
        raise NotFoundError("分类")


@router.get("/checklist-rules")
def list_rules(session: SessionDep) -> dict[str, Any]:
    rows = session.scalars(select(ChecklistRule).order_by(ChecklistRule.id))
    return ok([serialize_rule(row) for row in rows])


@router.post("/checklist-rules", dependencies=ADMIN_ONLY)
def create_rule(body: ChecklistRuleCreate, session: SessionDep) -> dict[str, Any]:
    _ensure_category(session, body.category_id)
    rule = ChecklistRule(
        category_id=body.category_id,
        attachment_kind=str(body.attachment_kind),
        level=str(body.level),
        condition=body.condition.to_json(),
        hint=body.hint,
    )
    session.add(rule)
    session.commit()
    return ok(serialize_rule(rule))


@router.patch("/checklist-rules/{rule_id}", dependencies=ADMIN_ONLY)
def update_rule(rule_id: int, body: ChecklistRuleUpdate, session: SessionDep) -> dict[str, Any]:
    rule = _rule_or_404(session, rule_id)
    values = present_values(body, nullable=("category_id",))
    if "category_id" in values:
        _ensure_category(session, values["category_id"])
        rule.category_id = values["category_id"]
    if "attachment_kind" in values:
        rule.attachment_kind = str(values["attachment_kind"])
    if "level" in values:
        rule.level = str(values["level"])
    if "condition" in values:
        rule.condition = values["condition"].to_json()
    if "hint" in values:
        rule.hint = values["hint"]
    session.commit()
    return ok(serialize_rule(rule))


@router.delete("/checklist-rules/{rule_id}", dependencies=ADMIN_ONLY)
def delete_rule(rule_id: int, session: SessionDep) -> dict[str, Any]:
    session.delete(_rule_or_404(session, rule_id))
    session.commit()
    return ok(None)
