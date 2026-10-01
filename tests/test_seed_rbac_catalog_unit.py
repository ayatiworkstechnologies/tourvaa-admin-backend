import ast
from pathlib import Path

from app import seed
from app.config import Settings


def test_every_literal_route_permission_is_seeded():
    """Prevent a protected endpoint from referencing an unseeded permission."""
    used = set()
    routers = Path(__file__).resolve().parents[1] / "app" / "routers"
    for path in routers.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if function_name not in {"require_permission", "require_any_permission"}:
                continue
            used.update(
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )

    seeded = {permission["slug"] for permission in seed.DEFAULT_PERMISSIONS}
    assert used <= seeded, f"Route permissions missing from seed: {sorted(used - seeded)}"


def test_every_granular_permission_module_is_seeded():
    module_slugs = {slug for slug, _ in seed.MODULES}
    permission_modules = {permission["module"] for permission in seed.DEFAULT_PERMISSIONS}
    assert permission_modules <= module_slugs


def test_bootstrap_login_settings_exist_for_all_admin_roles():
    fields = Settings.model_fields
    for prefix in ("SUPER_ADMIN", "ADMIN", "SUB_ADMIN"):
        assert f"{prefix}_NAME" in fields
        assert f"{prefix}_EMAIL" in fields
        assert f"{prefix}_PASSWORD" in fields
        assert f"{prefix}_RESET_PASSWORD_ON_STARTUP" in fields
