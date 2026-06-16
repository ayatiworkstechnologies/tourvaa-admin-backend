from module_tests.common import Step


STEPS = [
    Step("permissions list", "GET", "/permissions/"),
    Step("roles list", "GET", "/roles/"),
    Step("modules list no slash", "GET", "/modules"),
    Step("modules list slash", "GET", "/modules/"),
]
