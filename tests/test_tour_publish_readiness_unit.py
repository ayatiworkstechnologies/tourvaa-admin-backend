from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.cms import is_tour_publish_ready


def tour(*, supplier_id, status, tour_id=6):
    return SimpleNamespace(id=tour_id, supplier_id=supplier_id, status=status)


def test_admin_authored_tour_does_not_require_supplier_review():
    assert is_tour_publish_ready(tour(supplier_id=None, status="draft")) is True


def test_new_supplier_draft_is_not_publish_ready():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    with patch("sqlalchemy.orm.object_session", return_value=session):
        assert is_tour_publish_ready(tour(supplier_id=2, status="draft")) is False


def test_approved_disabled_supplier_tour_can_be_republished():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = (1,)
    with patch("sqlalchemy.orm.object_session", return_value=session):
        assert is_tour_publish_ready(tour(supplier_id=2, status="disabled")) is True
