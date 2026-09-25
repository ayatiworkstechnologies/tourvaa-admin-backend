import inspect

from app import seed


def test_supplier_seed_does_not_grant_customer_invoice_permissions():
    source = inspect.getsource(seed.seed_default_roles_and_permissions)
    supplier_section = source.split("supplier: [", 1)[1].split("agent_reseller: [", 1)[0]

    assert '"view-invoices"' not in supplier_section
    assert '"invoices.view"' not in supplier_section
    assert '"invoices.download"' not in supplier_section
