"""分类、经费项目、清单规则的接口形状。"""

from typing import Any

from invoice_sorting.db.models import Category, ChecklistRule, Project


def serialize_category(category: Category) -> dict[str, Any]:
    return {
        "id": category.id,
        "name": category.name,
        "color": category.color,
        "keywords": list(category.keywords or []),
        "route_hint": category.route_hint or "",
        "sort": category.sort,
        "archived": bool(category.archived),
    }


def serialize_project(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "code": project.code or "",
        "name": project.name,
        "owner": project.owner or "",
        "active": bool(project.active),
    }


def serialize_rule(rule: ChecklistRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "category_id": rule.category_id,
        "attachment_kind": rule.attachment_kind,
        "level": rule.level,
        "condition": dict(rule.condition or {}),
        "hint": rule.hint or "",
    }
