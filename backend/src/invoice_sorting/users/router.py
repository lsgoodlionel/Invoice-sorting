"""用户管理 API（仅管理员）。"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.auth.deps import ADMIN_ONLY, AdminDep
from invoice_sorting.common.errors import ok
from invoice_sorting.settings.deps import SessionDep
from invoice_sorting.users.repository import list_users
from invoice_sorting.users.schemas import PasswordReset, UserCreate, UserUpdate
from invoice_sorting.users.serializers import serialize_user
from invoice_sorting.users.service import (
    create_user,
    get_user_or_404,
    reset_user_password,
    update_user,
)

router = APIRouter(prefix="/api/users", tags=["用户管理"], dependencies=ADMIN_ONLY)


@router.get("")
def read_users(session: SessionDep) -> dict[str, Any]:
    return ok([serialize_user(user) for user in list_users(session)])


@router.post("")
def add_user(body: UserCreate, session: SessionDep) -> dict[str, Any]:
    user = create_user(session, body)
    session.commit()
    return ok(serialize_user(user))


@router.patch("/{user_id}")
def patch_user(
    user_id: int, body: UserUpdate, session: SessionDep, actor: AdminDep
) -> dict[str, Any]:
    user = update_user(session, actor, get_user_or_404(session, user_id), body)
    session.commit()
    return ok(serialize_user(user))


@router.post("/{user_id}/password")
def reset_password(user_id: int, body: PasswordReset, session: SessionDep) -> dict[str, Any]:
    reset_user_password(session, get_user_or_404(session, user_id), body.password)
    session.commit()
    return ok(None)
