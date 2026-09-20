"""设置 API：应用设置、备份，并挂载分类/项目/清单规则子路由。"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import ok
from invoice_sorting.config import Settings
from invoice_sorting.expenses.recompute import refresh_open_expenses
from invoice_sorting.settings import catalog, rules
from invoice_sorting.settings.deps import ConfigDep, EngineDep, SessionDep
from invoice_sorting.settings.schemas import AppSettingsUpdate, present_values
from invoice_sorting.settings.service import (
    REGION_KEYS,
    backup_database,
    get_app_settings,
    update_app_settings,
)

router = APIRouter(prefix="/api", tags=["设置"])
router.include_router(catalog.router)
router.include_router(rules.router)


def _with_paths(values: dict[str, Any], config: Settings) -> dict[str, Any]:
    return {**values, "data_dir": str(config.data_dir), "inbox_dir": str(config.inbox_dir)}


@router.get("/settings")
def read_settings(session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    return ok(_with_paths(get_app_settings(session), config))


@router.put("/settings", dependencies=ADMIN_ONLY)
def write_settings(
    body: AppSettingsUpdate, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    before = get_app_settings(session)
    values = update_app_settings(session, **present_values(body))
    if any(before[key] != values[key] for key in REGION_KEYS):
        refresh_open_expenses(session, config)
    session.commit()
    return ok(_with_paths(values, config))


@router.post("/backup", dependencies=ADMIN_ONLY)
def backup(config: ConfigDep, engine: EngineDep) -> dict[str, Any]:
    path = backup_database(config, engine)
    return ok({"file": str(path)})
