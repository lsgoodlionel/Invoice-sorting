"""分类与经费项目 API。删除操作为归档/停用，保留历史引用。"""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import ConflictError, NotFoundError, ok
from invoice_sorting.db.models import Category, Project
from invoice_sorting.settings.deps import SessionDep
from invoice_sorting.settings.schemas import (
    CategoryCreate,
    CategoryUpdate,
    ProjectCreate,
    ProjectUpdate,
    present_values,
)
from invoice_sorting.settings.serializers import serialize_category, serialize_project

router = APIRouter()


def _category_or_404(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise NotFoundError("分类")
    return category


def _project_or_404(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError("经费项目")
    return project


def _ensure_unique_name(session: Session, name: str, exclude_id: int | None = None) -> None:
    query = select(Category.id).where(Category.name == name)
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    if session.scalar(query) is not None:
        raise ConflictError(f"分类名称“{name}”已存在")


@router.get("/categories")
def list_categories(session: SessionDep) -> dict[str, Any]:
    rows = session.scalars(select(Category).order_by(Category.sort, Category.id))
    return ok([serialize_category(row) for row in rows])


@router.post("/categories", dependencies=ADMIN_ONLY)
def create_category(body: CategoryCreate, session: SessionDep) -> dict[str, Any]:
    _ensure_unique_name(session, body.name)
    next_sort = (session.scalar(select(func.max(Category.sort))) or 0) + 1
    category = Category(**body.model_dump(), sort=next_sort, archived=False)
    session.add(category)
    session.commit()
    return ok(serialize_category(category))


@router.patch("/categories/{category_id}", dependencies=ADMIN_ONLY)
def update_category(category_id: int, body: CategoryUpdate, session: SessionDep) -> dict[str, Any]:
    category = _category_or_404(session, category_id)
    values = present_values(body)
    if "name" in values:
        _ensure_unique_name(session, values["name"], exclude_id=category_id)
    for name, value in values.items():
        setattr(category, name, value)
    session.commit()
    return ok(serialize_category(category))


@router.delete("/categories/{category_id}", dependencies=ADMIN_ONLY)
def archive_category(category_id: int, session: SessionDep) -> dict[str, Any]:
    _category_or_404(session, category_id).archived = True
    session.commit()
    return ok(None)


@router.get("/projects")
def list_projects(session: SessionDep) -> dict[str, Any]:
    rows = session.scalars(select(Project).order_by(Project.id))
    return ok([serialize_project(row) for row in rows])


@router.post("/projects")
def create_project(body: ProjectCreate, session: SessionDep) -> dict[str, Any]:
    project = Project(**body.model_dump(), active=True)
    session.add(project)
    session.commit()
    return ok(serialize_project(project))


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, session: SessionDep) -> dict[str, Any]:
    project = _project_or_404(session, project_id)
    for name, value in present_values(body).items():
        setattr(project, name, value)
    session.commit()
    return ok(serialize_project(project))


@router.delete("/projects/{project_id}")
def deactivate_project(project_id: int, session: SessionDep) -> dict[str, Any]:
    _project_or_404(session, project_id).active = False
    session.commit()
    return ok(None)
