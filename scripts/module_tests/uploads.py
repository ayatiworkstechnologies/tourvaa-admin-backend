from module_tests.common import Step


STEPS = [
    Step("admin asset auth required", "POST", "/uploads/admin-asset", expected=(422,)),
]
