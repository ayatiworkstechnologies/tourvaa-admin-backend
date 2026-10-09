import inspect

from app.api import router as api_router
from app.routers import invoices


def test_supplier_invoice_routes_are_registered_separately_from_admin_invoices():
    """Supplier invoice access is ownership-scoped, not an admin permission grant."""
    assert invoices.supplier_router in api_router.OPERATIONS_ROUTERS
    paths = {route.path for route in invoices.supplier_router.routes}
    assert "/supplier/invoices" in paths
    assert "/supplier/invoices/{invoice_id}/download" in paths


def test_supplier_invoice_routes_require_a_supplier_profile_and_keep_actor_scope():
    source = inspect.getsource(invoices)

    assert "def _require_supplier" in source
    assert "is_supplier_user(current_user)" in source
    assert "list_invoices(db, params[\"page\"], params[\"limit\"], actor=actor)" in source
    assert "download_invoice_pdf(db, invoice_id, actor)" in source
