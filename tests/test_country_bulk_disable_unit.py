from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.main  # noqa: F401 - register related ORM models
from app.models.cms import Country
from app.routers.cms import bulk_disable_countries


def test_bulk_disable_filters_and_audits(monkeypatch):
    engine = create_engine("sqlite://")
    Country.__table__.create(engine)
    audit = []
    monkeypatch.setattr("app.services.audit.log_audit", lambda *args, **kwargs: audit.append(kwargs))
    with Session(engine) as db:
        db.add_all([
            Country(country_name="India", country_code="IN", status="active"),
            Country(country_name="Indonesia", country_code="ID", status="active"),
            Country(country_name="Canada", country_code="CA", status="active"),
        ])
        db.commit()
        result = bulk_disable_countries(request=None, search="India", db=db, current_user=SimpleNamespace(id=1))
        assert result["updated"] == 1
        assert db.query(Country).filter_by(country_code="IN").one().status == "inactive"
        assert db.query(Country).filter_by(country_code="ID").one().status == "active"
        assert len(audit) == 1
        result = bulk_disable_countries(request=None, search="", db=db, current_user=SimpleNamespace(id=1))
        assert result["updated"] == 2
