from sqlalchemy import func, select

from invoice_sorting.db.models import Category, ChecklistRule


def test_health_returns_envelope(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": {"status": "up"}, "error": None}


def test_default_categories_and_rules_are_seeded_once(app, session):
    assert session.scalar(select(func.count()).select_from(Category)) == 10
    rules = session.scalar(select(func.count()).select_from(ChecklistRule))
    assert rules > 0
    from invoice_sorting.db.seed import seed_defaults

    seed_defaults(session)
    assert session.scalar(select(func.count()).select_from(Category)) == 10
