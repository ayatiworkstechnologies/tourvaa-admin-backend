import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app" / "services" / "bookings.py"


def _imports_name(function: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom) and any((alias.asname or alias.name) == name for alias in node.names)
        for node in ast.walk(function)
    )


def test_supplier_postpone_and_notify_import_the_email_template_they_use():
    # Regression: both functions called booking_status_update_email without
    # importing it (other functions import it locally), so every call raised
    # NameError after the booking change was already committed -> HTTP 500.
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in ("supplier_postpone_booking", "supplier_notify_parties"):
        fn = functions[name]
        uses = any(isinstance(n, ast.Name) and n.id == "booking_status_update_email" for n in ast.walk(fn))
        assert uses and _imports_name(fn, "booking_status_update_email"), name
