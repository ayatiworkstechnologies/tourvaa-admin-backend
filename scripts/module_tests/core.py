from module_tests.common import Step


STEPS = [
    Step("health", "GET", "/health"),
    Step("current session", "GET", "/auth/me"),
    Step("dashboard me", "GET", "/dashboard/me"),
]
