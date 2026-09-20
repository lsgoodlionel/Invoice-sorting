"""邀请码 API：管理员生成/查看本账套邀请码，受邀人凭邀请码加入。

`/api/invites` 只操作**当前账套**（管理员管不到别的账套，平台级管理留给批次四）；
`/api/auth/join` 是公开端点，复用登录失败限制，防止穷举邀请码。
"""

from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.auth.http import USER_AGENT_HEADER, client_ip
from invoice_sorting.auth.ratelimit import LoginRateLimiter, minutes_label
from invoice_sorting.auth.router import grant_response
from invoice_sorting.auth.service import Grant
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep, TenantRowDep
from invoice_sorting.control.models import Invite
from invoice_sorting.invites.schemas import InviteCreate, JoinBody
from invoice_sorting.invites.service import (
    JoinRequest,
    create_invite,
    list_invites,
    redeem_invite,
)

router = APIRouter(tags=["邀请码"])


def serialize_invite(invite: Invite) -> dict[str, Any]:
    return {
        "id": invite.id,
        "code": invite.code,
        "role": invite.role,
        "expires_on": invite.expires_on.isoformat() if invite.expires_on else None,
        "is_used": invite.used_by is not None,
        "used_at": iso_datetime(invite.used_at),
        "created_at": iso_datetime(invite.created_at),
    }


@router.get("/api/invites", dependencies=ADMIN_ONLY)
def read_invites(control: ControlSessionDep, tenant: TenantRowDep) -> dict[str, Any]:
    return ok([serialize_invite(invite) for invite in list_invites(control, tenant.id)])


@router.post("/api/invites", dependencies=ADMIN_ONLY)
def post_invite(
    body: InviteCreate, control: ControlSessionDep, tenant: TenantRowDep
) -> dict[str, Any]:
    invite = create_invite(control, tenant.id, str(body.role), body.expires_on)
    control.flush()
    return ok(serialize_invite(invite))


@router.post("/api/auth/join")
def post_join(
    body: JoinBody, request: Request, response: Response, control: ControlSessionDep
) -> dict[str, Any]:
    """凭邀请码加入账套并登录：已有账号需填写其登录密码，新用户名则直接开户。"""
    limiter: LoginRateLimiter = request.app.state.login_limiter
    key = client_ip(request)
    wait = limiter.retry_after(key)
    if wait:
        raise AppError(f"尝试次数过多，请 {minutes_label(wait)} 分钟后再试", status_code=429)
    join = JoinRequest(
        code=body.code,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
    )
    grant = _redeem(request, control, join, limiter, key)
    limiter.reset(key)
    return grant_response(request, response, control, grant)


def _redeem(request: Request, control: Session, join: JoinRequest, limiter, key: str) -> Grant:
    """邀请码或密码不对都计入失败次数，防止穷举。"""
    try:
        user_agent = request.headers.get(USER_AGENT_HEADER, "")
        return redeem_invite(control, join, user_agent, request.app.state.settings)
    except AppError:
        limiter.record_failure(key)
        raise
