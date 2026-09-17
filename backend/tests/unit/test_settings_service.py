"""应用设置与数据库备份（T20）。"""

import sqlite3
from datetime import date

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.expenses.service import create_expense
from invoice_sorting.settings import service as settings_service
from invoice_sorting.settings.service import (
    backup_database,
    get_app_settings,
    update_app_settings,
)


def test_defaults(session):
    assert get_app_settings(session) == {"buyer_name": "", "buyer_tax_id": "", "overdue_days": 30}


def test_update_persists_values(session):
    result = update_app_settings(session, buyer_name="某某大学", overdue_days=45)
    assert result["buyer_name"] == "某某大学"
    assert get_app_settings(session)["overdue_days"] == 45
    update_app_settings(session, buyer_tax_id="12100000")
    assert get_app_settings(session) == {
        "buyer_name": "某某大学",
        "buyer_tax_id": "12100000",
        "overdue_days": 45,
    }


@pytest.mark.parametrize("values", [{"overdue_days": 0}, {"unknown": "x"}])
def test_update_rejects_invalid(session, values):
    with pytest.raises(AppError):
        update_app_settings(session, **values)


def test_backup_copies_database_and_keeps_latest_ten(app, session, settings, monkeypatch):
    create_expense(session, settings, spent_on=date(2026, 9, 1), amount_cents=960, merchant="京东")
    session.commit()
    stamps = iter(f"20260917_1200{i:02d}" for i in range(12))
    monkeypatch.setattr(settings_service, "_timestamp", lambda: next(stamps))

    paths = [backup_database(settings, app.state.engine) for _ in range(12)]

    remaining = sorted(settings.backup_dir.glob("invoice_*.db"))
    assert len(remaining) == 10
    assert paths[-1] in remaining and paths[0] not in remaining
    with sqlite3.connect(paths[-1]) as conn:
        assert conn.execute("select merchant, amount_cents from expense").fetchall() == [
            ("京东", 960)
        ]
